"""Offline checks for the bounded taught trial; no hardware connection is made."""

import contextlib
import io
import unittest
from scripts.taught_pick_trial import perform_cycle, validate_geometry

LOW = [200.0, 70.0, 95.0, 180.0, 0.0, 0.0]
HIGH = [200.0, 70.0, 97.0, 180.0, 0.0, 0.0]


class FakeArm:
    def __init__(self, seal=True, fail_motion=False):
        self.pose = LOW.copy()
        self.seal = seal
        self.fail_motion = fail_motion
        self.calls = []
        self.on = False

    def get_err_warn_code(self):
        return 0, [0, 0]

    def get_state(self):
        return 0, 2

    def get_position(self):
        return 0, self.pose.copy()

    def get_vacuum_gripper(self):
        return 0, (1 if self.seal else 0) if self.on else -1

    def get_tool_digital_input(self):
        return 0, [int(self.on and self.seal), 0, 0]

    def get_tgpio_output_digital(self):
        return 0, [int(self.on), int(not self.on), 0, 0, 0]

    def set_vacuum_gripper(self, on, **kwargs):
        self.calls.append(("vacuum", on))
        self.on = on
        return 0 if self.seal or not on else 41

    def set_position(self, *pose, **kwargs):
        self.calls.append(("move", list(pose)))
        if self.fail_motion:
            return 31
        self.pose = list(pose)
        return 0

    def __getattr__(self, name):
        raise AssertionError(f"Unexpected hardware call: {name}")


class TaughtCycle(unittest.TestCase):
    def run_quiet(self, arm):
        with contextlib.redirect_stdout(io.StringIO()):
            perform_cycle(arm, LOW, HIGH, [], sleep=lambda _: None)

    def test_authorized_speed_scale_changes_speed_only(self):
        arm = FakeArm()
        speeds = []
        move = arm.set_position

        def capture(*pose, **kwargs):
            speeds.append((kwargs["speed"], kwargs["mvacc"]))
            return move(*pose, **kwargs)

        arm.set_position = capture
        with contextlib.redirect_stdout(io.StringIO()):
            perform_cycle(arm, LOW, HIGH, [], sleep=lambda _: None, speed_scale=1.15)
        self.assertEqual(speeds, [(2.3, 5), (2.3, 5)])
        self.assertEqual(arm.pose, LOW)
        self.assertFalse(arm.on)

    def test_second_fifteen_percent_increase_preserves_path_and_seal_gate(self):
        arm = FakeArm()
        speeds = []
        move = arm.set_position

        def capture(*pose, **kwargs):
            speeds.append((kwargs["speed"], kwargs["mvacc"]))
            return move(*pose, **kwargs)

        arm.set_position = capture
        with contextlib.redirect_stdout(io.StringIO()):
            perform_cycle(arm, LOW, HIGH, [], sleep=lambda _: None, speed_scale=1.3225)
        self.assertEqual(speeds, [(2.645, 5), (2.645, 5)])
        self.assertEqual(arm.pose, LOW)
        self.assertFalse(arm.on)
        failed_seal = FakeArm(seal=False)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            perform_cycle(
                failed_seal, LOW, HIGH, [], sleep=lambda _: None, speed_scale=1.3225
            )
        self.assertFalse(any(call[0] == "move" for call in failed_seal.calls))

    def test_unapproved_speed_scale_rejected_before_tool_or_motion(self):
        arm = FakeArm()
        with self.assertRaises(ValueError):
            perform_cycle(arm, LOW, HIGH, [], speed_scale=1.3226)
        self.assertEqual(arm.calls, [])

    def test_success_is_single_lift_hold_lower_release(self):
        arm = FakeArm()
        self.run_quiet(arm)
        self.assertEqual(
            arm.calls,
            [
                ("vacuum", True),
                ("move", HIGH),
                ("move", LOW),
                ("vacuum", False),
            ],
        )
        self.assertFalse(arm.on)
        self.assertEqual(arm.pose, LOW)

    def test_explicit_small_drop_releases_after_only_upward_motion(self):
        arm = FakeArm()
        with contextlib.redirect_stdout(io.StringIO()):
            perform_cycle(
                arm, LOW, HIGH, [], sleep=lambda _: None, release_at_hover=True
            )
        self.assertEqual(
            arm.calls,
            [("vacuum", True), ("move", HIGH), ("vacuum", False)],
        )
        self.assertEqual(arm.pose, HIGH)
        self.assertFalse(arm.on)

    def test_pickup10_uses_known_contact_and_low_release_clearance(self):
        arm = FakeArm()
        arm.pose = HIGH.copy()  # Start at the earlier verified 2 mm hover.
        lift = LOW.copy()
        lift[2] += 10
        with contextlib.redirect_stdout(io.StringIO()):
            perform_cycle(
                arm,
                LOW,
                lift,
                [],
                sleep=lambda _: None,
                start_pose=HIGH,
                release_pose=HIGH,
            )
        self.assertEqual(
            arm.calls,
            [
                ("move", LOW),
                ("vacuum", True),
                ("move", lift),
                ("move", HIGH),
                ("vacuum", False),
            ],
        )
        self.assertEqual(arm.pose, HIGH)
        self.assertFalse(arm.on)

    def test_pickup10_failed_seal_never_moves_above_contact(self):
        arm = FakeArm(seal=False)
        arm.pose = HIGH.copy()
        lift = LOW.copy()
        lift[2] += 10
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            perform_cycle(
                arm,
                LOW,
                lift,
                [],
                sleep=lambda _: None,
                start_pose=HIGH,
                release_pose=HIGH,
            )
        self.assertEqual(
            [call for call in arm.calls if call[0] == "move"], [("move", LOW)]
        )
        self.assertFalse(arm.on)

    def test_no_attachment_means_no_lift_and_contact_cleanup(self):
        arm = FakeArm(seal=False)
        with self.assertRaises(RuntimeError):
            self.run_quiet(arm)
        self.assertFalse(any(call[0] == "move" for call in arm.calls))
        self.assertFalse(arm.on)

    def test_motion_failure_does_not_release_or_try_recovery_move(self):
        arm = FakeArm(fail_motion=True)
        with self.assertRaises(RuntimeError):
            self.run_quiet(arm)
        self.assertTrue(arm.on)
        self.assertEqual(sum(call[0] == "move" for call in arm.calls), 1)
        self.assertNotIn(("vacuum", False), arm.calls)

    def test_release_feedback_failure_never_reports_cycle_complete(self):
        arm = FakeArm()
        arm.get_tool_digital_input = lambda: (0, [1, 0, 0])
        events = []
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            perform_cycle(
                arm, LOW, HIGH, events, sleep=lambda _: None, release_at_hover=True
            )
        self.assertFalse(arm.on)
        self.assertNotIn("cycle_complete_at_hover", [e["event"] for e in events])
        self.assertEqual(arm.get_tgpio_output_digital()[1], [0, 1, 0, 0, 0])

    def test_geometry_rejects_long_or_sideways_motion(self):
        contact = {"pose_mm_degrees": LOW, "contact_observed_by_operator": True}
        self.assertEqual(
            validate_geometry(contact, {"pose_mm_degrees": HIGH}), (LOW, HIGH)
        )
        for invalid in (
            [201.0, 70.0, 97.0, 180.0, 0.0, 0.0],
            [200.0, 70.0, 110.0, 180.0, 0.0, 0.0],
        ):
            with self.assertRaises(ValueError):
                validate_geometry(contact, {"pose_mm_degrees": invalid})


if __name__ == "__main__":
    unittest.main()
