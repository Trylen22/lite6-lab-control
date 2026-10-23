"""Explicit, leased hand-puppy following on wrist joints 4 and 5.

Behavior (the operator starts it from the deck):
  open palm  -> the wrist turns so the palm moves toward the image center
  fist       -> pause and glide back to the ready pose, wait there
  no hand    -> hold still; after LOST_HOME_SECONDS glide back to ready
  Stop / page closed / heartbeat lost -> glide back to ready, then position mode

The "ready pose" is the joint pose when Start is pressed. Only joints 4 and 5
ever change; base, shoulder, elbow and wrist roll are held exactly.

Control: a velocity loop. The measured image Jacobian (pixels per degree of
J4/J5, from hand_calibrate.py) converts the palm's pixel error into a joint
velocity, which is rate- and acceleration-limited and integrated at 50 Hz into
servo-mode targets (hand_servo.py). The Jacobian is local and gives direction
and gain, not hand depth; closing the loop on fresh frames corrects for that.
No suction, fault resets, or Cartesian IK are involved.
"""

from datetime import datetime, timezone
import threading
import time
import uuid

import numpy as np

from .hand_space import load_hand_profile
from .calibration_motion import ROOT
from .hand_servo import HandServoArm
from .green_calibrate import save

TICK_SECONDS = 0.02  # 50 Hz servo stream
MAX_FRAME_AGE = 0.4
HEARTBEAT_TIMEOUT = 1.5
LOST_HOME_SECONDS = 3.0
# Travel allowed from the ready pose for J4, J5 (degrees).
FOLLOW_RANGE_DEG = np.array([30.0, 25.0])
# A start pose this far from the calibrated anchor makes the Jacobian unreliable.
MAX_ANCHOR_DRIFT_DEG = 15
MAX_SPEED_DEG_S = 20
MAX_ACCEL_DEG_S2 = 80
HOME_SPEED_DEG_S = 12
GAIN_PER_S = 1.5  # Fraction of remaining error closed per second.
DEAD_ZONE_PX = 12
RESUME_ZONE_PX = 18
IMAGE_CENTER = np.array([320.0, 200.0])
# One-hand lock: once a hand is tracked, only a hand within LOCK_GATE_PX of
# its last position counts, so a second hand (e.g. holding a phone to record)
# is ignored. The lock lapses after LOCK_TIMEOUT_S without seeing that hand.
LOCK_GATE_PX = 150
LOCK_TIMEOUT_S = 1.0
AXES = [3, 4]


def palm_width(hand):
    points = hand["landmarks"]
    return float(np.hypot(*(np.subtract(points[5], points[17]))))


def select_hand(hands, near=None):
    """Pick the tracked hand: nearest to `near` (within the gate) if locked,
    otherwise the largest (usually the hand closest to the camera)."""
    if near is None:
        return max(hands, key=palm_width)

    def distance(hand):
        return float(np.linalg.norm(np.subtract(hand["center"], near)))

    closest = min(hands, key=distance)
    return closest if distance(closest) <= LOCK_GATE_PX else None


def classify_hand(snapshot, profile, now=None, near=None):
    """Classify the tracked hand.

    Returns (kind, data, seq, tracked_center): ("open", center, ...),
    ("fist", center, ...) or ("none", reason, ...). tracked_center is the
    selected hand's center (None when no hand was selected); other hands
    in the image are ignored.
    """
    now = time.monotonic() if now is None else now
    if snapshot["settings"]["mode"] != "hands":
        return "none", "Select Hand puppy mode", None, None
    source = snapshot.get("source", {})
    sequence = source.get("sequence")
    if (
        not snapshot.get("fresh")
        or snapshot.get("resolution") != profile["resolution"]
        or not 0 <= now - source.get("received_monotonic", 0) <= MAX_FRAME_AGE
    ):
        return "none", "Camera frame stale", sequence, None
    hands = [
        hand
        for hand in snapshot["detections"]
        if np.shape(hand.get("landmarks")) == (21, 2)
        and np.shape(hand.get("center")) == (2,)
        and np.isfinite(hand["landmarks"]).all()
        and np.isfinite(hand["center"]).all()
    ]
    if not hands:
        return "none", "No hand in view", sequence, None
    hand = select_hand(hands, near)
    if hand is None:
        return "none", "Tracked hand left the view", sequence, None
    points = np.array(hand["landmarks"], dtype=float)
    center = np.array(hand["center"], dtype=float)
    # Finger straightness from landmarks: cosine of the knuckle-PIP-tip angle.
    # Straight ~ -1, folded back ~ +1. MediaPipe's gesture label alone often
    # says "None" for a perfectly open hand, so geometry decides too.
    bends = []
    for knuckle, pip, tip in [(5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]:
        first = points[knuckle] - points[pip]
        second = points[tip] - points[pip]
        norms = np.linalg.norm(first) * np.linalg.norm(second)
        bends.append(1.0 if norms < 1e-6 else float(np.dot(first, second) / norms))
    gesture, score = hand.get("gesture"), hand.get("confidence", 0)
    if (gesture == "Closed_Fist" and score >= 0.5) or min(bends) > 0:
        return "fist", center, sequence, center
    if palm_width(hand) < 15:
        return "none", "Hand too far away", sequence, center
    if not (0 <= center[0] < 640 and 0 <= center[1] < 400):
        return "none", "Palm left the image", sequence, center
    if (gesture == "Open_Palm" and score >= 0.5) or max(bends) < -0.6:
        return "open", center, sequence, center
    return (
        "none",
        "Open your hand to follow, close it to send home",
        sequence,
        center,
    )


class FollowPolicy:
    """Pure velocity controller: observe() frames, step() 50 Hz joint targets."""

    def __init__(self, profile, home):
        self.home = np.array(home[:6], dtype=float)
        self.command = self.home.copy()
        self.velocity = np.zeros(2)
        self.jinv = np.linalg.inv(np.array(profile["jacobian_px_per_degree"]))
        self.profile = profile
        self.mode = "hold"  # hold | follow | home
        self.filtered = None
        self.sequence = None
        self.stable = 0
        self.centered = True
        self.lost_since = None
        self.lock_center = None
        self.lock_time = None
        self.message = "Show an open palm"

    def observe(self, snapshot, now=None):
        now = time.monotonic() if now is None else now
        if self.lock_time is not None and now - self.lock_time > LOCK_TIMEOUT_S:
            self.lock_center = self.lock_time = None
        kind, data, sequence, tracked = classify_hand(
            snapshot, self.profile, now, near=self.lock_center
        )
        if tracked is not None:
            self.lock_center, self.lock_time = tracked, now
        if kind == "open":
            if sequence != self.sequence:
                self.sequence = sequence
                self.stable += 1
                self.filtered = (
                    data if self.filtered is None else 0.5 * data + 0.5 * self.filtered
                )
            self.lost_since = None
            if self.stable >= 2:
                self.mode = "follow"
                self.message = "Following your open palm"
            else:
                self.mode = "hold"
                self.message = "Palm found · confirming"
            return self.message
        self.filtered, self.stable, self.centered = None, 0, True
        if kind == "fist":
            self.mode, self.lost_since = "home", None
            self.message = "Fist · paused at ready pose"
            return self.message
        if self.mode != "home":
            self.lost_since = self.lost_since or now
            if now - self.lost_since >= LOST_HOME_SECONDS:
                self.mode = "home"
            else:
                self.mode = "hold"
        self.message = data if self.mode == "hold" else f"{data} · back at ready pose"
        return self.message

    def desired_velocity(self):
        if self.mode == "follow":
            error = IMAGE_CENTER - self.filtered
            distance = float(np.linalg.norm(error))
            if distance <= DEAD_ZONE_PX or (
                self.centered and distance <= RESUME_ZONE_PX
            ):
                self.centered = True
                return np.zeros(2)
            self.centered = False
            # Soft dead zone: speed ramps from zero at the dead-zone edge.
            error = error * (1 - DEAD_ZONE_PX / distance)
            velocity = GAIN_PER_S * (self.jinv @ error)
            limit = MAX_SPEED_DEG_S
        elif self.mode == "home":
            velocity = 2.0 * (self.home[AXES] - self.command[AXES])
            limit = HOME_SPEED_DEG_S
        else:
            return np.zeros(2)
        speed = np.linalg.norm(velocity)
        return velocity * (limit / speed) if speed > limit else velocity

    def step(self, dt=TICK_SECONDS):
        wanted = self.desired_velocity()
        change = wanted - self.velocity
        max_change = MAX_ACCEL_DEG_S2 * dt
        if np.linalg.norm(change) > max_change:
            change *= max_change / np.linalg.norm(change)
        self.velocity = self.velocity + change
        joints = self.command[AXES] + self.velocity * dt
        low = self.home[AXES] - FOLLOW_RANGE_DEG
        high = self.home[AXES] + FOLLOW_RANGE_DEG
        clipped = np.clip(joints, low, high)
        self.velocity[clipped != joints] = 0  # Stop pushing into the range edge.
        if self.mode == "home" and np.all(np.abs(clipped - self.home[AXES]) < 0.05):
            clipped, self.velocity = self.home[AXES].copy(), np.zeros(2)
        self.command[AXES] = clipped
        return self.command.tolist()

    def at_home(self):
        return bool(np.all(self.command == self.home)) and not self.velocity.any()


class HandFollower:
    def __init__(self, vision, profile_path=None, robot_factory=HandServoArm):
        self.vision = vision
        self.profile_path = profile_path
        self.robot_factory = robot_factory
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.heartbeat_time = 0.0
        self.token = None
        self.data = {
            "state": "idle",
            "message": "Select Hand puppy, then Start following",
        }

    def profile(self):
        from .hand_space import PROFILE

        if not (self.profile_path or PROFILE).exists():
            raise RuntimeError("Calibrate this hand-demo pose first")
        return (
            load_hand_profile(self.profile_path)
            if self.profile_path
            else load_hand_profile()
        )

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    @staticmethod
    def check_anchor(joints, profile):
        drift = np.abs(np.array(joints[:6]) - np.array(profile["anchor_joints_deg"]))
        if np.max(drift) > MAX_ANCHOR_DRIFT_DEG:
            raise RuntimeError(
                "Arm is far from the calibrated hand-demo pose; recalibrate"
            )

    def readiness(self, robot):
        try:
            profile = self.profile()
            if self.vision.snapshot()["settings"]["mode"] != "hands":
                return False, "Select Hand puppy mode"
            if not robot.get("fresh"):
                return False, "Robot telemetry unavailable"
            values = robot["values"]
            if values["errors"] != [0, 0]:
                return False, "Controller reports an error; clear it first"
            if values["state"] not in (2, 5):
                return False, f"Robot state {values['state']}; must be idle or stopped"
            self.check_anchor(values["joints"], profile)
            kind = classify_hand(self.vision.snapshot(), profile)[0]
            return True, (
                "Open palm in view · start following"
                if kind == "open"
                else "Ready · start, then show an open palm"
            )
        except (ValueError, RuntimeError, KeyError, OSError, TypeError) as exc:
            return False, str(exc)

    def start(self):
        profile = self.profile()
        with self.lock:
            if self.data["state"] == "running":
                raise RuntimeError("Following already active")
            self.stop_event.clear()
            self.token = uuid.uuid4().hex
            self.heartbeat_time = time.monotonic()
            self.data = {
                "state": "running",
                "message": "Connecting to the arm",
                "token": self.token,
                "started_utc": datetime.now(timezone.utc).isoformat(),
            }
            self.worker = threading.Thread(
                target=self._run, args=(profile,), daemon=False
            )
            self.worker.start()
            return self.data.copy()

    def heartbeat(self, token):
        with self.lock:
            if self.data["state"] != "running" or token != self.token:
                raise ValueError("This browser does not own an active follow session")
            self.heartbeat_time = time.monotonic()
        return self.snapshot()

    def stop(self):
        # Software stop: the arm glides back to the ready pose. Not an E-stop.
        self.stop_event.set()
        return self.snapshot()

    def join(self):
        self.stop()
        if self.worker:
            self.worker.join()

    def _set_message(self, message):
        with self.lock:
            self.data["message"] = message

    def _run(self, profile):
        record = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "samples": [],
            "profile_id": profile["profile_id"],
            "motion_kind": "wrist_servo_follow",
            "joint_axes": AXES,
            "units": "degrees",
        }
        path = (
            ROOT
            / "local/trial_logs"
            / datetime.now(timezone.utc).strftime("hand-follow-%Y%m%dT%H%M%S.json")
        )
        reason = "Stopped"
        try:
            with self.robot_factory() as robot:
                home = robot.joints()
                self.check_anchor(home, profile)
                policy = FollowPolicy(profile, home)
                for corner in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                    test = np.array(home, dtype=float)
                    test[AXES] += np.array(corner) * FOLLOW_RANGE_DEG
                    if not robot.within_limits(test.tolist()):
                        raise RuntimeError("Follow range reaches a joint limit")
                record["home"] = home
                robot.begin()
                tick = 0
                next_time = time.monotonic()
                while True:
                    now = time.monotonic()
                    with self.lock:
                        last_heartbeat = self.heartbeat_time
                    if self.stop_event.is_set():
                        break
                    if now - last_heartbeat > HEARTBEAT_TIMEOUT:
                        reason = "Browser heartbeat lost"
                        break
                    self._set_message(policy.observe(self.vision.snapshot()))
                    robot.servo(policy.step())
                    if tick % 25 == 0:
                        record["samples"].append(
                            {
                                "t": round(now, 3),
                                "mode": policy.mode,
                                "joints": [round(x, 3) for x in policy.command[AXES]],
                            }
                        )
                    tick += 1
                    next_time += TICK_SECONDS
                    time.sleep(max(0, next_time - time.monotonic()))
                # Orderly finish: glide back to the ready pose.
                self._set_message(f"{reason} · returning to ready pose")
                policy.mode = "home"
                deadline = time.monotonic() + 10
                while not policy.at_home() and time.monotonic() < deadline:
                    robot.servo(policy.step())
                    time.sleep(TICK_SECONDS)
                record["final_joints"] = robot.joints()
            record["result"] = "returned_to_ready"
            with self.lock:
                self.data.update(
                    state="stopped", message=f"{reason} · arm at ready pose"
                )
        except BaseException as exc:
            record.update(result="ended_no_recovery", error=str(exc))
            with self.lock:
                self.data.update(state="stopped", message=str(exc))
        finally:
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            save(path, record)
