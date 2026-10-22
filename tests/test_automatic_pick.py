"""Fake controller integration: complete cycle returns, failed seal never lifts."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from labdeck.automatic_pick import run_cycle
from test_pickup_jobs import profile_fixture


class FakeRobot:
    def __init__(self):
        self.pose = [200, 70, 266, 180, 0, 0]
        self.moves = []
        self.arm = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def check(self):
        return self.pose.copy()

    def preview(self, target):
        return {"start": self.pose.copy(), "target": target.copy()}

    def preview_path(self, targets):
        return {"targets": targets}

    def move(self, target, speed):
        self.moves.append(target.copy())
        self.pose = target.copy()


class AutomaticPickTests(unittest.TestCase):
    def run_fake(self, seal=True, session="fake-camera"):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            profile = root / "profile.json"
            profile.write_text(json.dumps(profile_fixture()))
            robot = FakeRobot()
            cycle_calls = []
            stack.enter_context(patch("labdeck.automatic_pick.ROOT", root))
            stack.enter_context(
                patch("labdeck.automatic_pick.CalibrationArm", return_value=robot)
            )
            observer = stack.enter_context(
                patch(
                    "labdeck.automatic_pick.observe",
                    return_value={
                        "center_px": [330, 60],
                        "session": session,
                        "resolution": [640, 400],
                        "sequence": 1,
                    },
                )
            )

            def search(arm, above, events, **kwargs):
                self.assertEqual(above[2], 100)  # Suction/search begins above floor.
                arm.pose[2] = 95
                return arm.pose.copy() if seal else None

            stack.enter_context(
                patch("labdeck.automatic_pick.search_contact", side_effect=search)
            )

            def perform(arm, low, lift, events, **kwargs):
                cycle_calls.append((low, lift, kwargs))
                events.append({"event": "release_io_verified"})
                arm.pose = kwargs["release_pose"].copy()

            stack.enter_context(
                patch("labdeck.automatic_pick.perform_cycle", side_effect=perform)
            )
            progress = []
            try:
                result = run_cycle(
                    profile,
                    progress=lambda *p: progress.append(p),
                    min_area=200,
                    execute=True,
                )
                error = None
            except RuntimeError as exc:
                result = None
                error = str(exc)
            return robot, cycle_calls, result, error, progress, observer.call_args_list

    def test_success_places_then_returns_to_camera_height(self):
        robot, calls, result, error, progress, observations = self.run_fake()
        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            robot.moves, [[200, 70, 100, 180, 0, 0], [200, 70, 266, 180, 0, 0]]
        )
        self.assertEqual(calls[0][2]["speed_scale"], 1.3225)
        self.assertEqual(result["final_pose"][2], 266)
        self.assertEqual(progress[-1][0], "complete")
        self.assertEqual(observations[0].kwargs["min_area"], 200)

    def test_failed_seal_does_not_lift_or_return_automatically(self):
        robot, calls, result, error, _, _ = self.run_fake(seal=False)
        self.assertIn("No seal", error)
        self.assertEqual(calls, [])
        self.assertEqual(len(robot.moves), 1)
        self.assertEqual(robot.pose[2], 95)

    def test_camera_session_change_prevents_all_movement(self):
        robot, calls, result, error, _, _ = self.run_fake(session="different-session")
        self.assertIn("Camera session changed", error)
        self.assertEqual(robot.moves, [])
        self.assertEqual(calls, [])
