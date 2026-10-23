"""Wrist-only commands cannot silently move shoulder joints or ignore stop intent."""

import unittest
from unittest.mock import Mock
from labdeck.hand_motion import HandWristArm


class HandMotionTests(unittest.TestCase):
    def test_shoulder_change_and_late_stop_prevent_command(self):
        robot = HandWristArm()
        anchor = [0, -10, 45, -60, -60, 60]
        robot.check = Mock(return_value=anchor)
        robot.arm = Mock()
        robot.arm.is_joint_limit.return_value = (0, False)
        robot.arm.get_forward_kinematics.return_value = (0, [200, 80, 420, 0, 0, 0])
        with self.assertRaisesRegex(RuntimeError, "only wrist"):
            robot.preview([1, -10, 45, -60, -60, 60])
        with self.assertRaisesRegex(RuntimeError, "exceeds 1 degree"):
            robot.move([0, -10, 45, -62, -60, 60], speed=2)

        def stop():
            raise RuntimeError("Stop requested")

        with self.assertRaisesRegex(RuntimeError, "Stop requested"):
            robot.move([0, -10, 45, -60.3, -60, 60], speed=2, authorize=stop)
        robot.arm.set_servo_angle.assert_not_called()
