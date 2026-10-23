"""Explicit, leased, fixed-wrist visual hand following.

No suction, wrist rotation, enabling, fault resets or queued trajectory.
The separately measured scene response supplies a centering direction: a hand
at another depth has a different metric scale. Small capped corrections, fresh
frames and a bounded wrist range limit the experiment; this is not 3D hand tracking.
"""

from datetime import datetime, timezone
import threading
import time
import uuid

import numpy as np

from .hand_space import load_hand_profile, check_hand_pose, check_hand_transit
from .calibration_motion import ROOT
from .hand_motion import HandWristArm
from .green_calibrate import save

MAX_FRAME_AGE = 0.4
HEARTBEAT_TIMEOUT = 1.5
MAX_SESSION_SECONDS = 90
MAX_RADIUS_DEGREES = 6
MAX_STEP_DEGREES = 0.3
FOLLOW_SPEED_DEG_S = 2
DEAD_ZONE_PX = 25


def hand_target(snapshot, profile, now=None):
    """Return one fresh open palm; uncertainty never supplies a motion target."""
    now = time.monotonic() if now is None else now
    if snapshot["settings"]["mode"] != "hands":
        raise RuntimeError("Select Hand puppy mode")
    source = snapshot.get("source", {})
    if (
        not snapshot.get("fresh")
        or source.get("session") != profile["camera_session"]
        or snapshot.get("resolution") != profile["resolution"]
        or not 0 <= now - source.get("received_monotonic", 0) <= MAX_FRAME_AGE
    ):
        raise RuntimeError("Hand frame stale or camera session changed")
    hands = snapshot["detections"]
    if len(hands) != 1:
        raise RuntimeError("Show exactly one open palm")
    hand = hands[0]
    if hand.get("gesture") != "Open_Palm" or hand.get("confidence", 0) < 0.5:
        raise RuntimeError("Open palm follows; other gestures pause")
    center = np.array(hand["center"], dtype=float)
    points = np.array(hand["landmarks"], dtype=float)
    if (
        center.shape != (2,)
        or points.shape != (21, 2)
        or not np.isfinite(points).all()
        or not np.isfinite(center).all()
    ):
        raise RuntimeError("Invalid hand landmarks")
    # A canned gesture score is not a calibrated probability. Combine the
    # Open_Palm class with explicit four-finger geometry rather than treating a
    # high arbitrary classifier cutoff as proof of an open hand.
    for knuckle, pip, tip in [(5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]:
        first = points[knuckle] - points[pip]
        second = points[tip] - points[pip]
        norms = np.linalg.norm(first) * np.linalg.norm(second)
        if norms < 1e-6 or np.dot(first, second) / norms > -0.75:
            raise RuntimeError(
                "Straighten all four fingers with palm facing the camera"
            )
    # Apparent size/edge rejection is NOT measured separation from the tool.
    # Keep the complete hand visible and away from the physical arm.
    if np.any(points < 4) or np.any(points > np.array([636, 396])):
        raise RuntimeError("Keep your whole hand visible inside the image")
    palm_width = np.linalg.norm(points[5] - points[17])
    if not 25 <= palm_width <= 170:
        raise RuntimeError("Hand scale outside the demo range")
    return center, source["sequence"]


class FollowPolicy:
    """Smoothing/dead zone and a per-session radius, independent of SDK calls."""

    def __init__(self, profile, origin):
        self.profile = profile
        self.origin = np.array(origin)[profile["joint_axes"]]
        self.filtered = None
        self.sequence = None
        self.stable = 0

    def reset(self):
        self.filtered = None
        self.stable = 0

    def target(self, snapshot, pose, now=None):
        try:
            center, sequence = hand_target(snapshot, self.profile, now)
        except RuntimeError:
            self.reset()
            raise
        if self.sequence is not None and sequence <= self.sequence:
            raise RuntimeError("Waiting for a new hand frame")
        self.sequence = sequence
        self.stable += 1
        self.filtered = (
            center if self.filtered is None else 0.4 * center + 0.6 * self.filtered
        )
        check_hand_pose(pose, self.profile)
        if self.stable < 3:
            return None, "Confirming three fresh open-palm frames"
        error = np.array([320, 200]) - self.filtered
        if np.linalg.norm(error) <= DEAD_ZONE_PX:
            return None, "Palm centered · holding still"
        delta = 0.12 * np.linalg.solve(self.profile["jacobian_px_per_degree"], error)
        if np.linalg.norm(delta) > MAX_STEP_DEGREES:
            delta *= MAX_STEP_DEGREES / np.linalg.norm(delta)
        target = pose.copy()
        axes = self.profile["joint_axes"]
        for index, axis in enumerate(axes):
            target[axis] += float(delta[index])
        if np.linalg.norm(np.array(target)[axes] - self.origin) > MAX_RADIUS_DEGREES:
            raise RuntimeError("Session travel boundary reached; stop and recenter")
        check_hand_transit(pose, target, self.profile)
        return target, "Following your open palm"


class HandFollower:
    def __init__(self, vision, profile_path=None, robot_factory=HandWristArm):
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

    def readiness(self, robot):
        try:
            profile = self.profile()
            if (
                not robot.get("fresh")
                or robot["values"]["state"] != 2
                or robot["values"]["errors"] != [0, 0]
            ):
                return False, "Robot must be connected and idle"
            check_hand_pose(robot["values"]["joints"][:6], profile)
            hand_target(self.vision.snapshot(), profile)
            return True, "Open palm ready · start explicitly to follow"
        except (ValueError, RuntimeError, KeyError, OSError, TypeError) as exc:
            return False, str(exc)

    def start(self):
        profile = self.profile()
        hand_target(self.vision.snapshot(), profile)
        with self.lock:
            if self.data["state"] == "running":
                raise RuntimeError("Following already active")
            self.stop_event.clear()
            self.token = uuid.uuid4().hex
            self.heartbeat_time = time.monotonic()
            self.data = {
                "state": "running",
                "message": "Checking hand and robot",
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
        # There is at most one <=0.3 degree turn in flight; stopping prevents the next.
        # This is not a physical emergency stop and sends no mode/state change.
        self.stop_event.set()
        return self.snapshot()

    def join(self):
        self.stop()
        if self.worker:
            self.worker.join()

    def _run(self, profile):
        record = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "events": [],
            "profile_id": profile["profile_id"],
            "camera_session": profile["camera_session"],
            "motion_kind": "wrist_joint_follow",
            "joint_axes": [3, 4],
            "units": "degrees",
        }
        path = (
            ROOT
            / "local/trial_logs"
            / datetime.now(timezone.utc).strftime("hand-follow-%Y%m%dT%H%M%S.json")
        )
        started = time.monotonic()
        try:
            with self.robot_factory() as robot:
                origin = robot.check()
                check_hand_pose(origin, profile)
                policy = FollowPolicy(profile, origin)
                record["origin"] = origin
                expected_pose = origin.copy()
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    with self.lock:
                        last_heartbeat = self.heartbeat_time
                    if now - last_heartbeat > HEARTBEAT_TIMEOUT:
                        raise RuntimeError("Browser heartbeat lost; following ended")
                    if now - started > MAX_SESSION_SECONDS:
                        raise RuntimeError(
                            "90-second demo finished; start a new session"
                        )
                    if datetime.now(timezone.utc) >= datetime.fromisoformat(
                        profile["expires_utc"]
                    ):
                        raise RuntimeError("Calibration session expired")
                    pose = robot.check()
                    check_hand_pose(pose, profile)
                    if not np.allclose(pose, expected_pose, atol=0.3, rtol=0):
                        raise RuntimeError(
                            "Arm moved outside the follow controller; session ended"
                        )
                    try:
                        target, message = policy.target(self.vision.snapshot(), pose)
                    except RuntimeError as exc:
                        # Lost/non-open hand pauses and resets stability. Bounds
                        # also pause rather than driving along a clipped edge.
                        target, message = None, str(exc)
                    with self.lock:
                        self.data["message"] = message
                    if target is not None:
                        # IK can take time. Re-read intent and a *current* frame
                        # immediately before sending the short move.
                        robot.preview(target)
                        hand_target(self.vision.snapshot(), profile)
                        if (
                            self.stop_event.is_set()
                            or time.monotonic() - self.heartbeat_time
                            > HEARTBEAT_TIMEOUT
                        ):
                            break

                        def authorize():
                            hand_target(self.vision.snapshot(), profile)
                            if (
                                self.stop_event.is_set()
                                or time.monotonic() - self.heartbeat_time
                                > HEARTBEAT_TIMEOUT
                            ):
                                raise RuntimeError(
                                    "Follow intent ended before movement"
                                )

                        robot.move(
                            target, speed=FOLLOW_SPEED_DEG_S, authorize=authorize
                        )
                        expected_pose = robot.check()
                        record["events"].append(
                            {
                                "event": "follow_move",
                                "target": target,
                                "elapsed_seconds": time.monotonic() - started,
                            }
                        )
                        save(path, record)
                    self.stop_event.wait(0.04)
                record["final_pose"] = robot.check()
            record["result"] = "stopped_no_automatic_return"
            with self.lock:
                self.data.update(
                    state="stopped",
                    message="Following stopped · arm holds its current position",
                )
        except BaseException as exc:
            record.update(result="ended_no_recovery", error=str(exc))
            with self.lock:
                self.data.update(state="stopped", message=str(exc))
        finally:
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            save(path, record)
