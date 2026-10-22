"""Speed authorization validates numbers without connecting to hardware."""

import unittest
from labdeck.motion_profile import validate_speed_scale


class MotionProfileTests(unittest.TestCase):
    def test_two_compounded_increases_are_allowed(self):
        self.assertEqual(validate_speed_scale(1.3225), 1.3225)
        self.assertEqual(validate_speed_scale(1.15), 1.15)
        self.assertEqual(validate_speed_scale(1), 1)

    def test_nonfinite_and_above_cap_values_are_rejected(self):
        for scale in [float("nan"), float("inf"), -float("inf"), 0.99, 1.3226]:
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                validate_speed_scale(scale)
