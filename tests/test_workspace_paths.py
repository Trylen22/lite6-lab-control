"""Workspace checks distinguish a union of corridors from its outer rectangle."""

import unittest
from unittest.mock import Mock

from labdeck.automatic_pick import check_observation_pose, check_transit
from labdeck.calibration_motion import CalibrationArm
from test_pickup_jobs import profile_fixture


class WorkspacePathTests(unittest.TestCase):
    def test_union_does_not_authorize_gap_or_shortcut(self):
        p = profile_fixture()
        p["xy_regions_mm"] = [[[100, 0], [160, 150]], [[140, 100], [300, 150]]]
        check_observation_pose([250, 120, 266, 180, 0, 0], p)
        with self.assertRaisesRegex(RuntimeError, "Outside"):
            check_observation_pose([250, 50, 266, 180, 0, 0], p)
        with self.assertRaisesRegex(RuntimeError, "Outside"):
            check_transit([120, 20, 266, 180, 0, 0], [280, 120, 266, 180, 0, 0], p)

    def test_chained_preview_tests_vertical_descent_not_diagonal(self):
        robot = CalibrationArm()
        robot.check = Mock(return_value=[200, 0, 266, 180, 0, 0])
        robot.arm = Mock()
        robot.arm.get_servo_angle.return_value = (0, [0] * 6)
        samples = []

        def ik(pose, **kwargs):
            samples.append(pose)
            return 0, [0] * 6

        robot.arm.get_inverse_kinematics.side_effect = ik
        robot.arm.is_joint_limit.return_value = (0, False)
        plan = robot.preview_path([[240, 0, 266, 180, 0, 0], [240, 0, 95, 180, 0, 0]])
        descending = [pose for pose in samples if pose[2] < 266]
        self.assertTrue(descending)
        self.assertTrue(all(pose[0] == 240 for pose in descending))
        self.assertEqual(len(plan["segments"]), 2)
        robot.arm.set_position.assert_not_called()
        robot.arm.get_inverse_kinematics.side_effect = lambda *a, **k: (0, [90] * 6)
        with self.assertRaisesRegex(RuntimeError, "branch jump"):
            robot.preview_path([[240, 0, 95, 180, 0, 0]])
        robot.arm.set_position.assert_not_called()
