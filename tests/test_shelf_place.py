"""Shelf carry tests use a fake SDK: segment order, base locking, vertical
set-down, seal loss and path floors."""

import unittest

import numpy as np

from labdeck.shelf_place import ShelfCarrier

ABOVE = [-78.0, 20.4, 130.2, -173.3, -59.9, 184.7]
DROP = [-78.0, 7.9, 98.2, -171.1, -40.6, 181.3]
HOME = [3.5, 20.3, 64.4, -179.5, -42.2, 180.8]
SHELF = {"above_drop_joints_deg": ABOVE, "drop_joints_deg": DROP}


class FakeSDK:
    """Tool-tip height is a made-up function of J3 so floors can be tested."""

    def __init__(self, joints):
        self.joints_now = list(joints)
        self.pose = [330.0, 0.0, 95.0, -179.4, -2.0, 2.5]
        self.outputs = [1, 0, 0, 0, 0]
        self.sealed = True
        self.moves = []
        self.drop_seal_after = None

    def get_err_warn_code(self):
        return 0, [0, 0]

    def get_state(self):
        return 0, 2

    def get_vacuum_gripper(self):
        return 0, int(self.sealed)

    def get_tool_digital_input(self):
        return 0, [int(self.sealed), 0]

    def get_tgpio_output_digital(self):
        return 0, list(self.outputs)

    def set_vacuum_gripper(self, enabled, **_):
        self.outputs = [1, 0, 0, 0, 0] if enabled else [0, 1, 0, 0, 0]
        self.sealed = bool(enabled) and self.sealed
        self.moves.append(("vacuum", enabled))
        return 0

    def get_servo_angle(self):
        return 0, self.joints_now + [0.0]

    def get_forward_kinematics(self, joints, **_):
        return 0, [0, 0, 300 + joints[2], 0, 0, 0]

    def is_joint_limit(self, joints, **_):
        return 0, False

    def get_position(self):
        return 0, list(self.pose)

    def set_position(self, *target, **_):
        self.pose = list(target)
        self.moves.append(("lift", target[2]))
        # Straight down/up between the above-drop and drop poses.
        for joints in (DROP, ABOVE):
            if abs(target[2] - (300 + joints[2])) < 1e-6:
                self.joints_now = list(joints)
        return 0

    def set_servo_angle(self, angle, **_):
        self.joints_now = list(angle)
        self.moves.append(("joints", list(angle)))
        if self.drop_seal_after == len([m for m in self.moves if m[0] == "joints"]):
            self.sealed = False
        return 0


def joint_moves(sdk):
    return [np.array(m[1]) for m in sdk.moves if m[0] == "joints"]


class ShelfCarrierTests(unittest.TestCase):
    def run_carry(self, sdk):
        carrier = ShelfCarrier(sdk, [], sleep=lambda _: None)
        return carrier.run(SHELF, 265, HOME)

    def test_rise_base_locked_turn_high_then_straight_down_release_and_back(self):
        sdk = FakeSDK(HOME)
        self.run_carry(sdk)
        lifts = [m[1] for m in sdk.moves if m[0] == "lift"]
        # 10 mm seal test, camera height, straight down onto the shelf, up.
        self.assertEqual(lifts, [105.0, 265, 300 + DROP[2], 300 + ABOVE[2]])
        rise, turn, turn_back, home = joint_moves(sdk)
        self.assertEqual(rise[0], HOME[0])  # base locked during the rise
        np.testing.assert_allclose(rise[1:], ABOVE[1:])
        np.testing.assert_allclose(turn, ABOVE)  # base only from the rise
        np.testing.assert_allclose(turn_back[1:], ABOVE[1:])
        self.assertEqual(turn_back[0], HOME[0])
        np.testing.assert_allclose(home, HOME)
        release = sdk.moves.index(("vacuum", False))
        self.assertEqual(sdk.moves[release - 1], ("lift", 300 + DROP[2]))

    def test_lost_seal_during_carry_stops_without_release_or_more_moves(self):
        sdk = FakeSDK(HOME)
        sdk.drop_seal_after = 2  # seal drops during the turn
        with self.assertRaisesRegex(RuntimeError, "attachment lost"):
            self.run_carry(sdk)
        self.assertEqual(len(joint_moves(sdk)), 2)
        self.assertNotIn(("vacuum", False), sdk.moves)

    def test_path_below_floor_is_refused_before_moving(self):
        sdk = FakeSDK(HOME)
        low = {
            "above_drop_joints_deg": ABOVE[:2] + [-40] + ABOVE[3:],
            "drop_joints_deg": DROP,
        }
        with self.assertRaisesRegex(RuntimeError, "dips below"):
            self.run_carry_with(sdk, low)
        self.assertEqual(len(joint_moves(sdk)), 0)

    def run_carry_with(self, sdk, shelf):
        return ShelfCarrier(sdk, [], sleep=lambda _: None).run(shelf, 265, HOME)


if __name__ == "__main__":
    unittest.main()
