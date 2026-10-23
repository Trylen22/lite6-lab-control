"""Streaming wrist control for the hand-puppy demo (xArm servo mode 1).

Why servo mode: position mode (mode 0) plans, accelerates and STOPS every
command, so a stream of tiny moves looks choppy. Servo mode executes only the
newest joint target, so a 50 Hz stream of small, rate-limited targets gives
continuous motion. The controller does NOT rate-limit servo targets itself;
the caller (FollowPolicy in hand_follow.py) must keep each step small.

Entering servo mode is a controller mode change (set_mode(1) + set_state(0)).
Leaving always restores position mode and ready state, so pickup and the
rest of the deck find the arm the way they expect. This also resumes a
software-stopped arm (state 5). It never clears faults (state 4 / error
codes): those still require the operator.
"""

import fcntl
import json
import time
import tomllib

import numpy as np
from xarm.wrapper import XArmAPI

from .calibration_motion import ROOT, value
from .suction import checked_vacuum

# Commanded vs reported joints may differ by lag (report rate ~5-10 Hz at up
# to ~20 deg/s). A larger gap means something resisted or moved the arm.
MAX_TRACKING_ERROR_DEG = 6
MAX_SERVO_STEP_DEG = 1.0  # Hard per-command cap, independent of the policy.


class HandServoArm:
    def __enter__(self):
        lock_path = ROOT / "local/calibration-motion.lock"
        self.lease = lock_path.open("w")
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise RuntimeError("Another controller owns the arm") from None
        config = tomllib.loads((ROOT / "local/lab.toml").read_text())
        self.reference = json.loads(
            (ROOT / "local/taught_poses/controller-tool-report.json").read_text()
        )
        self.arm = XArmAPI(
            config["robot"]["ip"],
            do_not_open=True,
            enable_report=True,
            report_type="rich",
            timed_comm=False,
        )
        self.servoing = False
        self.last = None
        try:
            self.arm.connect()
            time.sleep(0.5)  # Let the first rich reports arrive.
            self.check_setup()
            return self
        except BaseException:
            self.arm.disconnect()
            self.lease.close()
            raise

    def __exit__(self, *_):
        try:
            self.end()
        finally:
            self.arm.disconnect()
            self.lease.close()

    def check_setup(self):
        """Same mounting/tool invariants as pickup, but accept stopped state 5."""
        a = self.arm
        if value(a.get_err_warn_code()) != [0, 0]:
            raise RuntimeError("Controller reports an error/warning; clear it first")
        if value(a.get_state()) not in (2, 5) or a.mode != 0:
            raise RuntimeError("Arm must be idle or stopped in position mode")
        if (
            a.is_simulation_robot
            or not all(a.motor_enable_states[:6])
            or a.collision_sensitivity < 3
        ):
            raise RuntimeError("Robot configuration differs from supervised setup")
        if not np.allclose(
            a.tcp_offset, self.reference["tcp_offset_mm_degrees"], atol=0.001
        ):
            raise RuntimeError("Controller TCP offset changed")
        outputs = value(a.get_tgpio_output_digital())[:2]
        empty = value(a.get_tool_digital_input())[0] == 0
        if outputs == [0, 0] and empty:
            # An E-stop/reset clears both tool outputs. With nothing in the cup,
            # re-assert the manufacturer's release state (DO0=0, DO1=1). The
            # verified tool write needs a ready (state 2) arm, so resume a
            # software-stopped arm first; this never clears faults.
            if value(a.get_state()) == 5:
                if a.set_state(0) != 0:
                    raise RuntimeError("Controller refused ready state")
                time.sleep(0.3)
            if checked_vacuum(a, False, wait=False, sync=False) != 0:
                raise RuntimeError("Could not re-assert suction release")
            outputs = value(a.get_tgpio_output_digital())[:2]
        if outputs != [0, 1] or not empty:
            raise RuntimeError("Suction must be released (cup empty) before moving")

    def joints(self):
        return [float(x) for x in value(self.arm.get_servo_angle())[:6]]

    def within_limits(self, joints):
        return not value(self.arm.is_joint_limit(list(joints), is_radian=False))

    def begin(self):
        a = self.arm
        if a.set_mode(1) != 0 or a.set_state(0) != 0:
            raise RuntimeError("Controller refused servo mode")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if a.mode == 1 and value(a.get_state()) in (1, 2):
                self.servoing = True
                self.last = np.array(self.joints())
                return
            time.sleep(0.05)
        raise RuntimeError("Servo mode did not become ready")

    def servo(self, joints):
        """Send one joint target; raise on any fault or unexpected tracking."""
        a = self.arm
        target = np.array(joints, dtype=float)
        if np.max(np.abs(target - self.last)) > MAX_SERVO_STEP_DEG:
            raise RuntimeError("Servo step exceeds the per-command cap")
        if a.error_code or a.state == 4 or a.mode != 1:
            raise RuntimeError(f"Controller fault/mode change (error {a.error_code})")
        code = a.set_servo_angle_j(list(target) + [0.0], is_radian=False)
        if code != 0:
            raise RuntimeError(f"Servo command returned {code}")
        self.last = target
        reported = np.array(a.angles[:6], dtype=float)
        if np.max(np.abs(reported - target)) > MAX_TRACKING_ERROR_DEG:
            raise RuntimeError("Arm is not tracking commands; stopped")

    def end(self):
        if not self.servoing:
            return
        self.servoing = False
        # Position mode + ready: the arm holds where it is.
        self.arm.set_mode(0)
        self.arm.set_state(0)
