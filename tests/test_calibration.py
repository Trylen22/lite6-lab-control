"""Synthetic checks for axis signs, data quality and bounded image correction."""

import unittest

import numpy as np

from labdeck.calibration import correction_mm, fit_response


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.xy = np.array([(0, 0), (10, 0), (-10, 0), (0, 10), (0, -10), (10, 10)])
        self.j = np.array([[0.2, -3.0], [-2.8, -0.1]])
        self.aim = np.array([400.0, 210.0])
        self.pixels = self.aim + self.xy @ self.j.T

    def test_fit_and_correction_preserve_crossed_axis_signs(self):
        model = fit_response(self.xy, self.pixels)
        np.testing.assert_allclose(model["jacobian_px_per_mm"], self.j, atol=1e-10)
        np.testing.assert_allclose(model["aim_px"], self.aim)
        displaced = self.aim + self.j @ [1, -1]
        np.testing.assert_allclose(correction_mm(model, displaced, gain=1), [-1, 1])

    def test_step_is_bounded_by_norm(self):
        model = fit_response(self.xy, self.pixels)
        delta = correction_mm(model, [0, 0])
        self.assertAlmostEqual(np.linalg.norm(delta), 2)

    def test_degenerate_or_inconsistent_data_rejected(self):
        with self.assertRaises(ValueError):
            fit_response(np.zeros((6, 2)), self.pixels)
        bad = self.pixels.copy()
        bad[0] += 30
        with self.assertRaises(ValueError):
            fit_response(self.xy, bad)
        with self.assertRaises(ValueError):
            fit_response(self.xy, np.ones((6, 2)))


class MotionPreviewTests(unittest.TestCase):
    def test_discontinuous_ik_is_rejected_before_motion(self):
        from labdeck.calibration_motion import CalibrationArm

        class FakeIK:
            def get_servo_angle(self):
                return 0, [0] * 6

            def get_inverse_kinematics(self, *args, **kwargs):
                return 0, [0, 0, 0, 60, 0, 0]

            def is_joint_limit(self, *args, **kwargs):
                return 0, False

            def set_position(self, *args, **kwargs):
                raise AssertionError("Read-only planning must never move")

        robot = CalibrationArm()
        robot.check = lambda: [200, 70, 260, -179, -2, 2]
        robot.arm = FakeIK()
        with self.assertRaisesRegex(RuntimeError, "IK branch jump"):
            robot.preview([200, 70, 240, -179, -2, 2])

    def test_changed_orientation_is_rejected(self):
        from labdeck.calibration_motion import CalibrationArm

        robot = CalibrationArm()
        robot.check = lambda: [200, 70, 260, -179, -2, 2]
        with self.assertRaisesRegex(RuntimeError, "orientation fixed"):
            robot.preview([200, 70, 240, -175, -2, 2])
