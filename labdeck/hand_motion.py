"""Short, supervised wrist turns using the same release/health motion lease.

Joint commands avoid Cartesian IK branch changes. Only wrist joints 4 and 5 can
change; sampled joint limits and forward kinematics bound TCP displacement.
This is not obstacle detection. The operator clears the wrist/camera volume.
"""

import numpy as np
from .calibration_motion import CalibrationArm, value


class HandWristArm(CalibrationArm):
    def check(self):
        # Parent validates real pose, enabled/braked motors, mode, release,
        # queue, payload and offsets. Return six joint angles for this policy.
        CalibrationArm.check(self)
        return value(self.arm.get_servo_angle())[:6]

    def preview(self, target):
        start = self.check()
        if not np.allclose(
            np.array(start)[[0, 1, 2, 5]],
            np.array(target)[[0, 1, 2, 5]],
            atol=0.05,
            rtol=0,
        ):
            raise RuntimeError("Hand demo changes only wrist joints 4 and 5")
        if max(abs(np.array(target) - start)) > 12:
            raise RuntimeError("Wrist preview exceeds the bounded demo range")
        origin = value(
            self.arm.get_forward_kinematics(
                start, input_is_radian=False, return_is_radian=False
            )
        )
        for fraction in np.linspace(
            0, 1, max(2, int(np.ceil(max(abs(np.array(target) - start)) / 0.25)) + 1)
        )[1:]:
            joints = (np.array(start) + fraction * (np.array(target) - start)).tolist()
            if value(self.arm.is_joint_limit(joints, is_radian=False)):
                raise RuntimeError("Wrist joint limit")
            pose = value(
                self.arm.get_forward_kinematics(
                    joints, input_is_radian=False, return_is_radian=False
                )
            )
            if np.linalg.norm(np.array(pose[:3]) - origin[:3]) > 15:
                raise RuntimeError("Wrist step TCP displacement exceeds 15 mm")
        return {"start": start, "target": target}

    def move(self, target, speed=2, authorize=None):
        if not 0 < speed <= 2:
            raise ValueError("Wrist speed capped at 2 degrees/s")
        if max(abs(np.array(target) - self.check())) > 1.01:
            raise RuntimeError("Wrist move exceeds 1 degree; no command")
        plan = self.preview(target)
        if not np.allclose(self.check(), plan["start"], atol=0.05, rtol=0):
            raise RuntimeError("Arm changed during wrist planning")
        if authorize:
            authorize()
        code = self.arm.set_servo_angle(
            angle=target, speed=speed, mvacc=5, is_radian=False, wait=True, timeout=8
        )
        if code != 0:
            raise RuntimeError(f"Wrist motion returned {code}; no recovery move")
        if not np.allclose(self.check(), target, atol=0.15, rtol=0):
            raise RuntimeError("Wrist target not reached")
