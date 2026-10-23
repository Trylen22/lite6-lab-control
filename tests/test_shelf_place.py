"""Shelf carry tests use a fake SDK: segment order, base locking, seal loss."""

import unittest

import numpy as np

from labdeck.shelf_place import ShelfCarrier

TOP = [8.0, -0.3, 88.0, -180.1, -45.8, 175.2]
DROP = [-78.0, 7.9, 98.2, -171.1, -40.6, 181.3]
HOME = [3.5, 20.3, 64.4, -179.5, -42.2, 180.8]
SHELF = {"top_joints_deg": TOP, "drop_joints_deg": DROP}


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

    def test_rises_with_base_locked_turns_base_only_then_releases_and_returns(self):
        sdk = FakeSDK(HOME)
        self.run_carry(sdk)
        lifts = [m[1] for m in sdk.moves if m[0] == "lift"]
        self.assertEqual(lifts, [105.0, 265])  # 10 mm seal check, then camera
        rise, turn, reach, back, turn_back, home = joint_moves(sdk)
        self.assertEqual(rise[0], HOME[0])  # base locked during the rise
        np.testing.assert_allclose(rise[1:], TOP[1:])
        np.testing.assert_allclose(turn[1:], rise[1:])  # base only
        self.assertEqual(turn[0], DROP[0])
        np.testing.assert_allclose(reach, DROP)
        np.testing.assert_allclose(back, turn)
        np.testing.assert_allclose(turn_back[1:], TOP[1:])
        self.assertEqual(turn_back[0], HOME[0])
        np.testing.assert_allclose(home, HOME)
        release = sdk.moves.index(("vacuum", False))
        joints_before_release = [m for m in sdk.moves[:release] if m[0] == "joints"]
        self.assertEqual(len(joints_before_release), 3)

    def test_lost_seal_during_carry_stops_without_release_or_more_moves(self):
        sdk = FakeSDK(HOME)
        sdk.drop_seal_after = 2  # seal drops during the turn
        with self.assertRaisesRegex(RuntimeError, "attachment lost"):
            self.run_carry(sdk)
        self.assertEqual(len(joint_moves(sdk)), 2)
        self.assertNotIn(("vacuum", False), sdk.moves)

    def test_path_below_floor_is_refused_before_moving(self):
        sdk = FakeSDK(HOME)
        low_top = {"top_joints_deg": TOP, "drop_joints_deg": DROP[:2] + [70] + DROP[3:]}
        with self.assertRaisesRegex(RuntimeError, "dips below"):
            self.run_carry_with(sdk, low_top)
        self.assertEqual(len(joint_moves(sdk)), 2)

    def run_carry_with(self, sdk, shelf):
        return ShelfCarrier(sdk, [], sleep=lambda _: None).run(shelf, 265, HOME)


if __name__ == "__main__":
    unittest.main()
