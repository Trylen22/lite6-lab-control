"""Follow tests never open the SDK or camera: they exercise stale intent and bounds."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from labdeck.hand_follow import FollowPolicy, HandFollower
from test_pickup_jobs import profile_fixture


def hand_profile():
    profile = profile_fixture()
    profile.update(
        hand_schema=2,
        anchor_joints_deg=[0, -10, 45, -60, -60, 60],
        joint_axes=[3, 4],
        joint_min_deg=[-65, -65],
        joint_max_deg=[-55, -55],
        jacobian_px_per_degree=[[0, -8], [-8, 0]],
    )
    return profile


def frame(center=(220, 200), sequence=1):
    points = [[float(center[0]), float(center[1])] for _ in range(21)]
    points[0][1] += 40
    for base, offset in [(5, -30), (9, -10), (13, 10), (17, 30)]:
        for index, dy in enumerate([10, -5, -20, -35]):
            points[base + index] = [float(center[0] + offset), float(center[1] + dy)]
    return {
        "fresh": True,
        "settings": {"mode": "hands"},
        "resolution": [640, 400],
        "source": {
            "session": "fake-camera",
            "sequence": sequence,
            "received_monotonic": time.monotonic(),
        },
        "detections": [
            {
                "center": list(center),
                "landmarks": points,
                "gesture": "Open_Palm",
                "confidence": 0.9,
            }
        ],
    }


class FollowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.profile = hand_profile()
        self.pose = [0, -10, 45, -60, -60, 60]
        self.policy = FollowPolicy(self.profile, self.pose)

    def test_stable_frames_required_then_small_fixed_height_step(self):
        for sequence in [1, 2]:
            self.assertIsNone(
                self.policy.target(frame(sequence=sequence), self.pose)[0]
            )
        target, _ = self.policy.target(frame(sequence=3), self.pose)
        self.assertEqual(target[:3], self.pose[:3])
        self.assertEqual(target[5], self.pose[5])
        self.assertAlmostEqual(target[4], -60.3)
        with self.assertRaisesRegex(RuntimeError, "new hand frame"):
            self.policy.target(frame(sequence=3), self.pose)

    def test_lost_fist_multiple_stale_restart_and_edges_never_target(self):
        for problem in [
            "lost",
            "fist",
            "multiple",
            "stale",
            "session",
            "edge",
            "confidence",
        ]:
            sample = frame()
            if problem == "lost":
                sample["detections"] = []
            if problem == "fist":
                sample["detections"][0]["gesture"] = "Closed_Fist"
            if problem == "multiple":
                sample["detections"] *= 2
            if problem == "stale":
                sample["source"]["received_monotonic"] -= 1
            if problem == "session":
                sample["source"]["session"] = "changed"
            if problem == "edge":
                sample["detections"][0]["landmarks"][0][0] = -1
            if problem == "confidence":
                sample["detections"][0]["confidence"] = 0.2
            with self.subTest(problem=problem), self.assertRaises(RuntimeError):
                self.policy.target(sample, self.pose)
            self.assertEqual(self.policy.stable, 0)

    def test_dead_zone_holds_and_radius_blocks(self):
        for sequence in [1, 2, 3]:
            target, message = self.policy.target(frame((320, 200), sequence), self.pose)
            self.assertIsNone(target)
        self.assertIn("centered", message)
        self.policy.filtered = None
        moved = self.pose.copy()
        moved[3] = -64.3
        moved[4] = -64.3
        with self.assertRaisesRegex(RuntimeError, "Session travel boundary"):
            self.policy.target(frame(sequence=4), moved)

    def test_medium_score_open_palm_requires_straight_fingers(self):
        sample = frame()
        sample["detections"][0]["confidence"] = 0.60
        self.assertIsNone(self.policy.target(sample, self.pose)[0])
        bent = frame(sequence=2)
        bent["detections"][0]["landmarks"][8] = bent["detections"][0]["landmarks"][
            5
        ].copy()
        with self.assertRaisesRegex(RuntimeError, "Straighten"):
            self.policy.target(bent, self.pose)

    def test_fist_resets_three_frame_gate(self):
        self.policy.target(frame(sequence=1), self.pose)
        self.policy.target(frame(sequence=2), self.pose)
        fist = frame(sequence=3)
        fist["detections"][0]["gesture"] = "Closed_Fist"
        with self.assertRaises(RuntimeError):
            self.policy.target(fist, self.pose)
        self.assertIsNone(self.policy.target(frame(sequence=4), self.pose)[0])


class FreshVision:
    def __init__(self):
        self.sequence = 0

    def snapshot(self):
        self.sequence += 1
        return frame(sequence=self.sequence)


class FakeRobot:
    def __init__(self):
        self.pose = [0, -10, 45, -60, -60, 60]
        self.moves = []
        self.on_move = lambda: None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def check(self):
        return self.pose.copy()

    def preview(self, target):
        return {"target": target}

    def move(self, target, speed, authorize=None):
        if authorize:
            authorize()
        self.moves.append((target, speed))
        self.pose = target.copy()
        self.on_move()


class FollowWorkerTests(unittest.TestCase):
    def test_explicit_start_moves_then_stop_prevents_another_step(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
        ):
            path = Path(folder) / "profile.json"
            path.write_text(json.dumps(hand_profile()))
            robot = FakeRobot()
            follower = HandFollower(FreshVision(), path, lambda: robot)
            self.assertEqual(robot.moves, [])
            robot.on_move = follower.stop
            state = follower.start()
            with self.assertRaises(ValueError):
                follower.heartbeat("wrong-token")
            follower.heartbeat(state["token"])
            follower.worker.join(2)
            self.assertFalse(follower.worker.is_alive())
            self.assertEqual(len(robot.moves), 1)
            self.assertEqual(robot.moves[0][1], 2)
            self.assertEqual(follower.snapshot()["state"], "stopped")

    def test_stop_during_ik_prevents_the_pending_move(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
        ):
            path = Path(folder) / "profile.json"
            path.write_text(json.dumps(hand_profile()))
            robot = FakeRobot()
            follower = HandFollower(FreshVision(), path, lambda: robot)
            robot.preview = lambda target: follower.stop()
            follower.start()
            follower.worker.join(2)
            self.assertFalse(follower.worker.is_alive())
            self.assertEqual(robot.moves, [])

    def test_missing_browser_heartbeat_ends_before_any_move(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
        ):
            path = Path(folder) / "profile.json"
            path.write_text(json.dumps(hand_profile()))
            robot = FakeRobot()
            follower = HandFollower(FreshVision(), path, lambda: robot)
            with patch("labdeck.hand_follow.HEARTBEAT_TIMEOUT", 0.01):
                follower.start()
                follower.worker.join(2)
            self.assertFalse(follower.worker.is_alive())
            self.assertEqual(robot.moves, [])
            self.assertIn("heartbeat lost", follower.snapshot()["message"])
