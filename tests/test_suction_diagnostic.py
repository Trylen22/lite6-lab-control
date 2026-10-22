"""Stationary diagnostic checks with a fake tool; no physical device involved."""

import unittest
from scripts.check_suction import pulse


class FakeTool:
    def __init__(self):
        self.on = False
        self.calls = []

    def get_position(self):
        return 0, [200, 70, 95, 180, 0, 0]

    def get_state(self):
        return 0, 2

    def get_err_warn_code(self):
        return 0, [0, 0]

    def get_cmdnum(self):
        return 0, 0

    def get_vacuum_gripper(self):
        return 0, 0 if self.on else -1

    def get_tool_digital_input(self):
        return 0, [0, 0, 0]

    def get_tgpio_output_digital(self):
        return 0, [int(self.on), int(not self.on), 0, 0, 0]

    def set_vacuum_gripper(self, on, **kwargs):
        self.on = on
        self.calls.append(("vacuum", on))
        return 0

    def __getattr__(self, name):
        raise AssertionError(f"Unexpected hardware call: {name}")


class StationaryDiagnostic(unittest.TestCase):
    def test_no_seal_logs_inputs_and_returns_tool_off_without_any_movement(self):
        tool = FakeTool()
        samples = []
        pulse(tool, [200, 70, 95, 180, 0, 0], samples, sleep=lambda _: None)
        self.assertEqual(tool.calls, [("vacuum", True), ("vacuum", False)])
        self.assertEqual(sum(row["phase"] == "on" for row in samples), 20)
        self.assertFalse(tool.on)

    def test_moved_pose_refuses_even_suction(self):
        tool = FakeTool()
        with self.assertRaises(RuntimeError):
            pulse(tool, [220, 70, 95, 180, 0, 0], [], sleep=lambda _: None)
        self.assertEqual(tool.calls, [])


if __name__ == "__main__":
    unittest.main()
