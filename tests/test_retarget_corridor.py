"""Pure checks for the new travel corridor; never connects to hardware."""

import unittest
import numpy as np
from labdeck.retarget_green import correction_in_corridor


class RetargetCorridorTests(unittest.TestCase):
    def setUp(self):
        self.start = [270, 75, 266, -179, -2, 2]
        self.destination = [310, -20, 266, -179, -2, 2]

    def test_both_xy_directions_supported_without_height_change(self):
        target = correction_in_corridor(
            self.start, np.array([2, -5]), self.start, self.destination
        )
        self.assertEqual(target, [272, 70, 266, -179, -2, 2])

    def test_outside_corridor_and_nonfinite_targets_rejected(self):
        for delta in [
            np.array([70, 0]),
            np.array([0, -120]),
            np.array([float("nan"), 0]),
        ]:
            with self.subTest(delta=delta), self.assertRaises(RuntimeError):
                correction_in_corridor(self.start, delta, self.start, self.destination)

    def test_lowered_or_rotated_pose_rejected(self):
        for index in [2, 3, 4, 5]:
            pose = self.start.copy()
            pose[index] += 2
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                correction_in_corridor(pose, np.zeros(2), self.start, self.destination)
