"""Move between the two demo start poses when the operator picks a demo tab.

  pickup start: camera height over the checked green-pickup table region,
                joints stored in ignored local/start-poses.json
  hand start:   the calibrated hand-puppy anchor (local/hand-follow.json)

Why stored joints, not a Cartesian target: the same tool pose has several
joint solutions (wrist "flips"). The controller's own IK picked one that spun
the wrist ~238 degrees from the hand pose. The stored solution is the branch
every validated pickup ran in (J4 near -180, J6 near +180); see SESSION_LOG.

Every move is a single joint-space move (mode 0) at a modest speed. Before it
is sent, the straight joint path is sampled: no joint limits, and forward
kinematics must keep the tool tip at or above MIN_TRANSFER_Z_MM the whole way
(both start poses sit at ~265-420 mm; the table contact floor is ~94 mm).
The pickup target is also checked by FK against the pickup profile's
observation height/orientation/region. FK sampling is not obstacle detection:
keep the swept volume clear.
"""

from datetime import datetime, timezone
import json
import threading
import time

import numpy as np

from .automatic_pick import check_observation_pose, load_profile
from .calibration_motion import ROOT, value
from .green_calibrate import save
from .hand_servo import HandServoArm
from .hand_space import load_hand_profile

POSES = ROOT / "local/start-poses.json"
MIN_TRANSFER_Z_MM = 250
TRANSFER_SPEED_DEG_S = 25
TRANSFER_ACCEL_DEG_S2 = 60
ARRIVED_DEG = 0.2


class TransferArm(HandServoArm):
    def fk(self, joints):
        return value(
            self.arm.get_forward_kinematics(
                list(joints), input_is_radian=False, return_is_radian=False
            )
        )

    def ready_position_mode(self):
        """Resume a software-stopped arm (state 5) in position mode. No faults."""
        a = self.arm
        if a.set_mode(0) != 0 or a.set_state(0) != 0:
            raise RuntimeError("Controller refused position mode")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if a.mode == 0 and value(a.get_state()) == 2:
                return
            time.sleep(0.05)
        raise RuntimeError("Arm did not become ready")

    def check_path(self, start, target):
        start, target = np.array(start, dtype=float), np.array(target, dtype=float)
        for fraction in np.linspace(0, 1, 61):
            joints = (start + fraction * (target - start)).tolist()
            if not self.within_limits(joints):
                raise RuntimeError("Path to start pose reaches a joint limit")
            if self.fk(joints)[2] < MIN_TRANSFER_Z_MM:
                raise RuntimeError(
                    f"Path dips below {MIN_TRANSFER_Z_MM} mm; raise the arm first"
                )

    def go(self, target):
        start = self.joints()
        if np.max(np.abs(np.array(start) - target)) <= ARRIVED_DEG:
            return False
        self.check_path(start, target)
        self.ready_position_mode()
        if not np.allclose(self.joints(), start, atol=0.1, rtol=0):
            raise RuntimeError("Arm moved during planning")
        travel = float(np.max(np.abs(np.array(start) - target)))
        code = self.arm.set_servo_angle(
            angle=list(target),
            speed=TRANSFER_SPEED_DEG_S,
            mvacc=TRANSFER_ACCEL_DEG_S2,
            is_radian=False,
            wait=True,
            timeout=travel / TRANSFER_SPEED_DEG_S + 10,
        )
        if code != 0:
            raise RuntimeError(f"Move to start returned {code}; no recovery move")
        if not np.allclose(self.joints(), target, atol=ARRIVED_DEG, rtol=0):
            raise RuntimeError("Start pose not reached")
        return True


def start_joints(task, poses_path=POSES):
    if task == "hand":
        return np.array(load_hand_profile()["anchor_joints_deg"], dtype=float)
    if task == "pickup":
        return np.array(
            json.loads(poses_path.read_text())["pickup_start_joints_deg"], dtype=float
        )
    raise ValueError("Unknown start pose")


class StartPoseMover:
    """Single-flight worker, same pattern as the pickup and follow workers."""

    def __init__(self, robot_factory=TransferArm, poses_path=POSES):
        self.robot_factory = robot_factory
        self.poses_path = poses_path
        self.lock = threading.Lock()
        self.worker = None
        self.data = {"state": "idle", "task": None, "message": ""}

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    def running(self):
        return self.snapshot()["state"] == "running"

    def start(self, task):
        target = start_joints(task, self.poses_path)
        with self.lock:
            if self.data["state"] == "running":
                raise RuntimeError("Already moving to a start pose")
            label = "pickup start" if task == "pickup" else "hand-demo pose"
            self.data = {
                "state": "running",
                "task": task,
                "message": f"Moving to {label}…",
            }
            self.worker = threading.Thread(
                target=self._run, args=(task, target, label), daemon=False
            )
            self.worker.start()
            return self.data.copy()

    def wait(self):
        if self.worker:
            self.worker.join()

    def _run(self, task, target, label):
        record = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "target_joints": target.tolist(),
        }
        try:
            with self.robot_factory() as robot:
                if task == "pickup":
                    check_observation_pose(robot.fk(target), load_profile())
                record["start_joints"] = robot.joints()
                moved = robot.go(target)
                record["final_joints"] = robot.joints()
            record["result"] = "moved" if moved else "already_there"
            message = f"At {label}" if moved else f"Already at {label}"
            with self.lock:
                self.data.update(state="done", message=message)
        except BaseException as exc:
            record.update(result="failed", error=str(exc))
            with self.lock:
                self.data.update(state="failed", message=str(exc))
        finally:
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            save(
                ROOT
                / "local/trial_logs"
                / datetime.now(timezone.utc).strftime("start-pose-%Y%m%dT%H%M%S.json"),
                record,
            )
