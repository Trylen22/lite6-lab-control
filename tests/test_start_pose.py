"""Start-pose tests use a fake arm: path checks, already-there, and exclusion."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from labdeck.start_pose import StartPoseMover, TransferArm

HAND = [6.9, -14.9, 48.7, -67.1, -67.6, 58.6]
PICKUP = [3.5, 20.3, 64.4, -179.5, -42.2, 180.8]


class FakeSDK:
    """Tool tip height is a made-up function of J2 so paths can dip."""

    def __init__(self, joints, low_dip=False, z=300):
        self.angles = list(joints)
        self.low_dip = low_dip
        self.z = z
        self.rises = []
        self.mode = 0
        self.moves = []

    def get_position(self):
        return 0, [300, 0, self.z, 180, 0, 0]

    def set_position(self, *target, **_):
        self.z = target[2]
        self.rises.append(target[2])
        return 0

    def get_forward_kinematics(self, joints, **_):
        if list(joints) == self.angles:
            return 0, [290, 20, self.z, -179.4, -2.05, 2.48]
        z = 300 - (120 if self.low_dip and 0 < joints[1] < 10 else 0)
        return 0, [290, 20, z, -179.4, -2.05, 2.48]

    def is_joint_limit(self, joints, **_):
        return 0, False

    def get_servo_angle(self):
        return 0, self.angles + [0.0]

    state = 2
    errors = [0, 0]

    def get_state(self):
        return 0, self.state

    def get_err_warn_code(self):
        return 0, self.errors

    def set_mode(self, mode):
        self.mode = mode
        return 0

    def set_state(self, state):
        if state == 0 and self.errors == [0, 0]:
            self.state = 2
        return 0

    def set_servo_angle(self, angle, **kwargs):
        self.moves.append((angle, kwargs["speed"]))
        self.angles = list(angle)
        return 0


def fake_arm(sdk):
    arm = TransferArm.__new__(TransferArm)
    arm.arm = sdk
    arm.servoing = False
    return arm


class TransferArmTests(unittest.TestCase):
    def test_moves_once_then_reports_already_there(self):
        sdk = FakeSDK(HAND)
        arm = fake_arm(sdk)
        self.assertTrue(arm.go(np.array(PICKUP)))
        self.assertEqual(sdk.moves, [(PICKUP, 25)])
        self.assertFalse(arm.go(np.array(PICKUP)))
        self.assertEqual(len(sdk.moves), 1)

    def test_already_there_after_power_up_still_leaves_arm_idle(self):
        # Power-up leaves the arm stopped (state 5) at the parked pose. The
        # demo click must ready it without moving, so Pick & Place can run.
        sdk = FakeSDK(PICKUP)
        sdk.state = 5
        self.assertFalse(fake_arm(sdk).go(np.array(PICKUP)))
        self.assertEqual(sdk.state, 2)
        self.assertEqual(sdk.moves, [])

    def test_controller_error_is_not_cleared_by_a_demo_click(self):
        sdk = FakeSDK(PICKUP)
        sdk.state, sdk.errors = 5, [1, 0]
        with self.assertRaisesRegex(RuntimeError, "clear it in Studio"):
            fake_arm(sdk).go(np.array(PICKUP))
        self.assertEqual(sdk.state, 5)

    def test_big_base_swing_or_wrist_spin_is_refused(self):
        shelf = [-78.3, 7.9, 98.2, -171.1, -40.6, 181.3]
        sdk = FakeSDK(shelf)
        with self.assertRaisesRegex(RuntimeError, "Base would swing"):
            fake_arm(sdk).go(np.array(PICKUP))
        jogged = [3.5, 20.3, 64.4, 0.5, 42.2, 0.8]  # same tool pose, other branch
        sdk = FakeSDK(jogged)
        with self.assertRaisesRegex(RuntimeError, "Wrist would spin"):
            fake_arm(sdk).go(np.array(PICKUP))
        self.assertEqual(sdk.moves, [])

    def test_low_arm_in_front_rises_straight_up_before_moving(self):
        sdk = FakeSDK(HAND, z=225)
        self.assertTrue(fake_arm(sdk).go(np.array(PICKUP)))
        self.assertEqual(sdk.rises, [270])
        self.assertEqual(sdk.moves, [(PICKUP, 25)])

    def test_low_arm_not_in_front_is_refused(self):
        side = [-60.0] + HAND[1:]
        sdk = FakeSDK(side, z=225)
        with self.assertRaisesRegex(RuntimeError, "not in front"):
            fake_arm(sdk).go(np.array([-55.0] + HAND[1:]))
        self.assertEqual((sdk.rises, sdk.moves), ([], []))

    def test_path_that_dips_toward_table_is_refused(self):
        sdk = FakeSDK(HAND, low_dip=True)
        with self.assertRaisesRegex(RuntimeError, "dips below"):
            fake_arm(sdk).go(np.array(PICKUP))
        self.assertEqual(sdk.moves, [])


class FakeArmContext:
    def __init__(self, joints=HAND):
        self.joints_now = list(joints)
        self.targets = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def joints(self):
        return self.joints_now

    def fk(self, joints):
        return [290, 20, 265.717163, -179.397268, -2.048553, 2.482282]

    def go(self, target):
        self.targets.append(list(target))
        self.joints_now = list(target)
        return True


class MoverTests(unittest.TestCase):
    def test_pickup_task_checks_profile_and_moves(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.start_pose.ROOT", Path(folder)),
            patch("labdeck.start_pose.load_profile") as profile,
            patch("labdeck.start_pose.check_observation_pose") as check,
        ):
            poses = Path(folder) / "start-poses.json"
            poses.write_text(json.dumps({"pickup_start_joints_deg": PICKUP}))
            robot = FakeArmContext()
            mover = StartPoseMover(lambda: robot, poses)
            mover.start("pickup")
            mover.wait()
            check.assert_called_once()
            profile.assert_called_once()
            self.assertEqual(robot.targets, [PICKUP])
            self.assertEqual(mover.snapshot()["message"], "At pickup start")

    def test_unknown_task_rejected(self):
        with self.assertRaises(ValueError):
            StartPoseMover(FakeArmContext).start("elsewhere")


if __name__ == "__main__":
    unittest.main()
