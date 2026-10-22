"""Regress live observed ON ACK/both-low condition without hardware."""

import unittest
from labdeck.suction import checked_vacuum


class LostPairArm:
    def __init__(self):
        self.outputs = [0, 1, 0, 0, 0]
        self.writes = []

    def get_state(self):
        return 0, 2

    def get_err_warn_code(self):
        return 0, [0, 0]

    def get_tgpio_output_digital(self):
        return 0, self.outputs.copy()

    def get_tool_digital_input(self):
        return 0, [0, 0, 0]

    def set_vacuum_gripper(self, *args, **kwargs):
        self.outputs = [0, 0, 0, 0, 0]  # Paired API ACK, observed wrong output state.
        return 0

    def set_tgpio_digital(self, channel, state, **kwargs):
        self.writes.append((channel, state))
        self.outputs[channel] = state
        return 0


class SuctionOutputsTests(unittest.TestCase):
    def test_lost_pair_is_repaired_and_verified_before_success(self):
        arm = LostPairArm()
        self.assertEqual(checked_vacuum(arm, True, sleep=lambda _: None), 0)
        self.assertEqual(arm.outputs, [1, 0, 0, 0, 0])
        self.assertEqual(arm.writes, [(1, 0), (0, 1)])

    def test_commanded_on_still_requires_independent_seal(self):
        arm = LostPairArm()
        self.assertEqual(checked_vacuum(arm, True, wait=True, sleep=lambda _: None), 41)
        self.assertEqual(arm.outputs, [1, 0, 0, 0, 0])

    def test_failed_individual_write_never_claims_success(self):
        arm = LostPairArm()
        arm.set_tgpio_digital = lambda *args, **kwargs: 31
        self.assertEqual(checked_vacuum(arm, True, sleep=lambda _: None), 31)
