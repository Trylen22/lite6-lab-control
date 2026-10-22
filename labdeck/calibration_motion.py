"""Narrow motion boundary for supervised, tool-OFF calibration.

No enabling, resets, mode changes, tool commands, or automatic recovery.
IK checks establish reachability/branch continuity, NOT obstacle clearance.
An operator must clear the swept volume and remain at the physical E-stop.
"""

import json
import fcntl
from pathlib import Path
import threading
import time
import tomllib
import urllib.request

import numpy as np
from xarm.wrapper import XArmAPI

ROOT = Path(__file__).resolve().parents[1]


def value(result):
    code, payload = result
    if code != 0:
        raise RuntimeError(f"SDK read returned {code}")
    return payload


class CalibrationArm:
    def __enter__(self):
        # Cooperating CLI processes share one motion lease; Studio is external.
        lock_path = ROOT / "local/calibration-motion.lock"
        self.lease = lock_path.open("w")
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise RuntimeError("Another calibration controller owns the arm") from None
        config = tomllib.loads((ROOT / "local/lab.toml").read_text())
        self.reference = json.loads(
            (ROOT / "local/taught_poses/controller-tool-report.json").read_text()
        )
        self.report = threading.Event()
        self.report_time = 0.0
        self.arm = XArmAPI(
            config["robot"]["ip"],
            do_not_open=True,
            enable_report=True,
            report_type="rich",
            timed_comm=False,
        )

        def received(*_):
            self.report_time = time.monotonic()
            self.report.set()

        self.arm.register_report_callback(received)
        try:
            self.arm.connect()
            for _ in range(2):
                self.report.clear()
                if not self.report.wait(3):
                    raise RuntimeError("No fresh rich reports")
            self.check()
            return self
        except BaseException:
            self.arm.disconnect()
            self.lease.close()
            raise

    def __exit__(self, *_):
        self.arm.disconnect()
        self.lease.close()

    def check(self):
        a = self.arm
        if time.monotonic() - self.report_time > 1:
            raise RuntimeError("Robot report stale")
        if (
            a.mode != 0
            or value(a.get_state()) != 2
            or value(a.get_err_warn_code()) != [0, 0]
        ):
            raise RuntimeError("Requires healthy idle position mode")
        if (
            a.is_simulation_robot
            or not all(a.motor_enable_states[:6])
            or not all(a.motor_brake_states[:6])
            or a.collision_sensitivity < 3
        ):
            raise RuntimeError("Robot configuration differs from supervised setup")
        for actual, key in [
            (a.tcp_offset, "tcp_offset_mm_degrees"),
            (a.world_offset, "world_offset_mm_degrees"),
        ]:
            if not np.allclose(actual, self.reference[key], atol=0.001, rtol=0):
                raise RuntimeError("Controller coordinate offsets changed")
        if a.tcp_load != self.reference["tcp_load_kg_and_cog_mm"]:
            raise RuntimeError("Tool load changed")
        if value(a.get_cmdnum()) != 0:
            raise RuntimeError("Another command is queued")
        if (
            value(a.get_tgpio_output_digital()) != [0, 1, 0, 0, 0]
            or value(a.get_tool_digital_input())[0] != 0
        ):
            raise RuntimeError("Requires verified release outputs and pickup input low")
        return value(a.get_position())

    def preview(self, target):
        """Preview one segment from the live pose without sending a move."""
        return self.preview_path([target])["segments"][0]

    def preview_path(self, targets):
        """Chain hypothetical IK seeds across segments, including a descent.

        Reading IK for a low endpoint directly from today's high pose would
        check a diagonal. Chaining checks the actual high transit, vertical
        descent and return, while leaving the physical arm stationary.
        """
        start = self.check()
        live_start = start.copy()
        for target in targets:
            if not np.allclose(start[3:], target[3:], atol=0.3, rtol=0):
                raise RuntimeError("Calibration must keep wrist orientation fixed")
        joints = value(self.arm.get_servo_angle())
        segments = []
        for target in targets:
            count = max(
                1, int(np.ceil(np.linalg.norm(np.array(target[:3]) - start[:3]) / 5))
            )
            worst = 0
            for fraction in np.linspace(0, 1, count + 1)[1:]:
                pose = (
                    np.array(start) + fraction * (np.array(target) - start)
                ).tolist()
                solution = value(
                    self.arm.get_inverse_kinematics(
                        pose,
                        input_is_radian=False,
                        return_is_radian=False,
                        limited=False,
                        ref_angles=joints[:6],
                    )
                )
                jump = max(abs(x - y) for x, y in zip(solution, joints))
                if jump > 10 or value(
                    self.arm.is_joint_limit(solution, is_radian=False)
                ):
                    raise RuntimeError("IK branch jump or joint limit; no move")
                worst = max(worst, jump)
                joints = solution
            segments.append(
                {"start": start, "target": target, "max_joint_step_deg": worst}
            )
            start = target.copy()
        if not np.allclose(self.check(), live_start, atol=0.1, rtol=0):
            raise RuntimeError("Pose changed during planning")
        return {"start": live_start, "segments": segments}

    def move(self, target, speed=5):
        with urllib.request.urlopen(
            "http://127.0.0.1:8090/health", timeout=1
        ) as response:
            camera = json.load(response)
        if not camera["fresh"] or camera["age_seconds"] > 0.5:
            raise RuntimeError("Camera stale; no calibration movement")
        plan = self.preview(target)
        print(json.dumps({"move": plan, "speed_mm_s": speed}), flush=True)
        # A second check rejects operator changes during IK computation.
        if not np.allclose(self.check(), plan["start"], atol=0.1, rtol=0):
            raise RuntimeError("Pose changed during planning")
        # Timeout must cover travel at the selected speed plus acceleration and
        # SDK settling. A fixed 8 s timeout is insufficient for 20 mm at 2 mm/s.
        distance = float(np.linalg.norm(np.array(target[:3]) - plan["start"][:3]))
        timeout = max(8, distance / speed + 3)
        code = self.arm.set_position(
            *target, speed=speed, mvacc=10, is_radian=False, wait=True, timeout=timeout
        )
        if code != 0:
            raise RuntimeError(f"Movement returned {code}; no recovery move")
        if not np.allclose(self.check(), target, atol=0.3, rtol=0):
            raise RuntimeError("Reached pose differs from target")
