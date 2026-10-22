"""Speed authorization validates numbers without connecting to hardware."""

import unittest
from labdeck.motion_profile import validate_speed_scale, clear_travel_speed


class MotionProfileTests(unittest.TestCase):
    def test_two_compounded_increases_are_allowed(self):
        self.assertEqual(validate_speed_scale(1.3225), 1.3225)
        self.assertEqual(validate_speed_scale(1.15), 1.15)
        self.assertEqual(validate_speed_scale(1), 1)

    def test_nonfinite_and_above_cap_values_are_rejected(self):
        for scale in [float("nan"), float("inf"), -float("inf"), 0.99, 1.3226]:
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                validate_speed_scale(scale)


class ClearTravelTests(unittest.TestCase):
    def test_default_legacy_rate_and_separate_empty_tool_cap(self):
        self.assertEqual(clear_travel_speed({"speed_scale": 1.3225}), 6.6125)
        self.assertEqual(
            clear_travel_speed({"speed_scale": 1.3225, "clear_travel_mm_s": 20}), 20
        )
        for speed in [float("nan"), float("inf"), True, 20.1, 0, 6]:
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                clear_travel_speed({"speed_scale": 1.3225, "clear_travel_mm_s": speed})
