"""No hardware: check floor enforcement and seal-before-lift boundary."""

import unittest

from labdeck.contact_pick import search_contact


class FakeContactArm:
    def __init__(self, seal_z=None, fail_move=False):
        self.pose = [260, 70, 100, -179, -2, 2]
        self.outputs = [0, 1, 0, 0, 0]
        self.seal_z = seal_z
        self.fail_move = fail_move
        self.moves = []

    def get_position(self):
        return 0, self.pose.copy()

    def get_state(self):
        return 0, 2

    def get_err_warn_code(self):
        return 0, [0, 0]

    def get_cmdnum(self):
        return 0, 0

    def get_tgpio_output_digital(self):
        return 0, self.outputs

    def get_tool_digital_input(self):
        return 0, [
            int(
                self.outputs[0] == 1
                and self.seal_z is not None
                and self.pose[2] <= self.seal_z
            ),
            0,
            0,
        ]

    def get_vacuum_gripper(self):
        return 0, self.get_tool_digital_input()[1][0]

    def set_vacuum_gripper(self, enabled, **kwargs):
        self.outputs = [1, 0, 0, 0, 0] if enabled else [0, 1, 0, 0, 0]
        return 0

    def set_tgpio_digital(self, channel, state, **kwargs):
        self.outputs[channel] = state
        return 0

    def set_position(self, *pose, **kwargs):
        self.moves.append(list(pose))
        if self.fail_move:
            return 100
        self.pose = list(pose)
        return 0


class ContactSearchTests(unittest.TestCase):
    def test_no_seal_never_crosses_five_mm_floor_and_releases(self):
        arm = FakeContactArm()
        result = search_contact(arm, arm.pose.copy(), [], sleep=lambda _: None)
        self.assertIsNone(result)
        self.assertEqual(len(arm.moves), 10)
        self.assertEqual(min(p[2] for p in arm.moves), 95)
        self.assertEqual(arm.outputs, [0, 1, 0, 0, 0])

    def test_seal_stops_descent_with_no_implicit_lift(self):
        arm = FakeContactArm(seal_z=99)
        result = search_contact(arm, arm.pose.copy(), [], sleep=lambda _: None)
        self.assertEqual(result[2], 99)
        self.assertEqual(len(arm.moves), 2)
        self.assertEqual(arm.outputs, [1, 0, 0, 0, 0])

    def test_uncertain_motion_does_not_release_or_recover_blindly(self):
        arm = FakeContactArm(fail_move=True)
        with self.assertRaisesRegex(RuntimeError, "no recovery move"):
            search_contact(arm, arm.pose.copy(), [], sleep=lambda _: None)
        self.assertEqual(len(arm.moves), 1)
        self.assertEqual(arm.outputs, [1, 0, 0, 0, 0])


class SuctionTransitionTests(unittest.TestCase):
    def test_delayed_output_state_settles_before_any_motion(self):
        class Delayed(FakeContactArm):
            reads = 0

            def get_tgpio_output_digital(self):
                if self.outputs[0]:
                    self.reads += 1
                    if self.reads < 3:
                        return 0, [0, 1, 0, 0, 0]
                return super().get_tgpio_output_digital()

            def set_position(self, *pose, **kwargs):
                assert self.reads >= 3
                return super().set_position(*pose, **kwargs)

        arm = Delayed(seal_z=99.5)
        contact = search_contact(arm, arm.pose.copy(), [], sleep=lambda _: None)
        self.assertEqual(contact[2], 99.5)
        self.assertEqual(len(arm.moves), 1)

    def test_outputs_never_on_means_no_movement(self):
        arm = FakeContactArm()
        arm.get_tgpio_output_digital = lambda: (0, [0, 1, 0, 0, 0])
        with self.assertRaisesRegex(RuntimeError, "readback"):
            search_contact(arm, arm.pose.copy(), [], sleep=lambda _: None)
        self.assertEqual(arm.moves, [])
        self.assertEqual(arm.outputs, [0, 1, 0, 0, 0])
