"""Return must be vertical, ascending and gated on verified tool release."""

import unittest
from labdeck.cycle_return import return_to_observation


class FakeReleasedRobot:
    def __init__(self):
        self.pose = [310, -20, 97, -179, -2, 2]
        self.moves = []

    def check(self):
        return self.pose.copy()

    def move(self, target, speed):
        self.moves.append((target.copy(), speed))
        self.pose = target.copy()


class CycleReturnTests(unittest.TestCase):
    def test_returns_up_without_changing_xy_or_wrist(self):
        robot = FakeReleasedRobot()
        events = []
        final = return_to_observation(robot, 266, 6.6125, events)
        self.assertEqual(final, [310, -20, 266, -179, -2, 2])
        self.assertEqual(robot.moves, [(final, 6.6125)])
        self.assertEqual(events[-1]["event"], "returned_to_observation")

    def test_release_check_failure_prevents_return(self):
        robot = FakeReleasedRobot()

        def fail():
            raise RuntimeError("Pickup input still asserted")

        robot.check = fail
        with self.assertRaises(RuntimeError):
            return_to_observation(robot, 266, 6.6125, [])
        self.assertEqual(robot.moves, [])

    def test_return_never_descends_from_above_observation_height(self):
        robot = FakeReleasedRobot()
        robot.pose[2] = 280
        with self.assertRaises(RuntimeError):
            return_to_observation(robot, 266, 6.6125, [])
        self.assertEqual(robot.moves, [])
