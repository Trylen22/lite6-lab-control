"""Follow tests never open the SDK or camera: they exercise gestures, the
velocity loop in a simulated scene, and the worker's start/stop/return path."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from labdeck import hand_follow
from labdeck.hand_follow import (
    LOCK_TIMEOUT_S,
    FollowPolicy,
    HandFollower,
    classify_hand,
)
from test_pickup_jobs import profile_fixture

HOME = [0, -10, 45, -60, -60, 60]


def hand_profile():
    profile = profile_fixture()
    profile.update(
        hand_schema=2,
        anchor_joints_deg=HOME,
        joint_axes=[3, 4],
        joint_min_deg=[-65, -65],
        joint_max_deg=[-55, -55],
        jacobian_px_per_degree=[[3.9, 6.6], [-5.8, 3.7]],
    )
    return profile


def frame(center=(220, 200), sequence=1, gesture="Open_Palm", fist=False):
    points = [[float(center[0]), float(center[1])] for _ in range(21)]
    points[0][1] += 40
    for base, offset in [(5, -30), (9, -10), (13, 10), (17, 30)]:
        # Knuckle, PIP, DIP, tip. A fist folds the tip back past the knuckle.
        dys = [10, -5, 0, 15] if fist else [10, -5, -20, -35]
        for index, dy in enumerate(dys):
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
                "gesture": gesture,
                "confidence": 0.9,
            }
        ],
    }


class ClassifyTests(unittest.TestCase):
    def test_open_fist_and_unlabeled(self):
        profile = hand_profile()
        self.assertEqual(classify_hand(frame(), profile)[0], "open")
        self.assertEqual(classify_hand(frame(gesture="None"), profile)[0], "open")
        self.assertEqual(
            classify_hand(frame(gesture="Closed_Fist"), profile)[0], "fist"
        )
        self.assertEqual(
            classify_hand(frame(gesture="None", fist=True), profile)[0], "fist"
        )

    def test_missing_stale_and_multiple_never_follow(self):
        profile = hand_profile()
        lost = frame()
        lost["detections"] = []
        stale = frame()
        stale["source"]["received_monotonic"] -= 1
        for sample in [lost, stale]:
            self.assertEqual(classify_hand(sample, profile)[0], "none")


def two_hands(tracked, other, sequence=1, other_gesture="Closed_Fist", scale=1.0):
    sample = frame(tracked, sequence)
    extra = frame(other, sequence, gesture=other_gesture)["detections"][0]
    # Scale the second hand's landmarks about its center (apparent size).
    extra["landmarks"] = [
        [other[0] + scale * (x - other[0]), other[1] + scale * (y - other[1])]
        for x, y in extra["landmarks"]
    ]
    sample["detections"].append(extra)
    return sample


class HandLockTests(unittest.TestCase):
    def test_unlocked_picks_largest_hand(self):
        profile = hand_profile()
        sample = two_hands((220, 200), (500, 300), other_gesture="Open_Palm", scale=2)
        kind, center, _, _ = classify_hand(sample, profile)
        self.assertEqual((kind, list(center)), ("open", [500, 300]))

    def test_second_hand_fist_is_ignored_while_locked(self):
        policy = FollowPolicy(hand_profile(), HOME)
        for seq in range(1, 4):
            policy.observe(frame((220, 200), seq))
        for seq in range(4, 40):
            # A bigger second hand making a fist never steals or homes the arm.
            policy.observe(two_hands((220, 200), (520, 320), seq, scale=2))
            policy.step()
        self.assertEqual(policy.mode, "follow")
        self.assertLess(np.linalg.norm(policy.lock_center - [220, 200]), 1)

    def test_lock_does_not_jump_to_other_hand_then_lapses(self):
        policy = FollowPolicy(hand_profile(), HOME)
        base = time.monotonic()

        def at(sample, offset):
            sample["source"]["received_monotonic"] = base + offset
            return policy.observe(sample, now=base + offset)

        at(frame((220, 200), 1), 0)
        at(frame((220, 200), 2), 0.1)
        self.assertIn("Tracked hand left", at(frame((520, 320), 3), 0.2))
        self.assertEqual(policy.mode, "hold")
        at(frame((520, 320), 4), 0.3 + LOCK_TIMEOUT_S)
        self.assertLess(np.linalg.norm(policy.lock_center - [520, 320]), 1)


class FollowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = FollowPolicy(hand_profile(), HOME)
        self.sequence = 0

    def run_ticks(self, policy, sample, ticks):
        for tick in range(ticks):
            sample["source"]["sequence"] = self.sequence = self.sequence + 1
            sample["source"]["received_monotonic"] = time.monotonic()
            policy.observe(sample)
            joints = policy.step()
        return joints

    def test_only_wrist_joints_move_and_steps_stay_small(self):
        previous = np.array(HOME, dtype=float)
        for seq in range(1, 200):
            self.policy.observe(frame((100, 80), seq))
            joints = np.array(self.policy.step())
            self.assertTrue(
                np.allclose(joints[[0, 1, 2, 5]], np.array(HOME)[[0, 1, 2, 5]])
            )
            self.assertLessEqual(np.max(np.abs(joints - previous)), 0.41)
            previous = joints
        self.assertGreater(np.max(np.abs(joints - HOME)), 2)

    def test_range_is_clamped(self):
        for seq in range(1, 2000):
            self.policy.observe(frame((5, 5), seq))
            joints = np.array(self.policy.step())
        travel = np.abs(joints[[3, 4]] - np.array(HOME)[[3, 4]])
        self.assertTrue(np.all(travel <= hand_follow.FOLLOW_RANGE_DEG + 1e-9))

    def test_closed_loop_centers_palm_with_camera_lag(self):
        # Simulated static palm: pixel = start + J (q - home), seen 5 ticks late.
        jacobian = np.array(hand_profile()["jacobian_px_per_degree"])
        start = np.array([200.0, 120.0])
        history = [np.array(HOME, dtype=float)] * 5
        for tick in range(400):
            seen = start + jacobian @ (history[0][[3, 4]] - np.array(HOME)[[3, 4]])
            self.policy.observe(frame(tuple(seen), sequence=tick // 3))
            history = history[1:] + [np.array(self.policy.step())]
        final = start + jacobian @ (history[-1][[3, 4]] - np.array(HOME)[[3, 4]])
        self.assertLess(np.linalg.norm(final - [320, 200]), 20)

    def test_fist_returns_home_and_lost_hand_holds_then_homes(self):
        self.run_ticks(self.policy, frame((100, 80)), 100)
        self.assertNotEqual(self.policy.command.tolist(), HOME)
        self.run_ticks(self.policy, frame((100, 80), gesture="Closed_Fist"), 600)
        self.assertTrue(self.policy.at_home())
        self.assertEqual(self.policy.mode, "home")
        moved = self.run_ticks(self.policy, frame((100, 80)), 100)
        lost = frame()
        lost["detections"] = []
        self.policy.observe(lost, now=1000)
        held = self.policy.step()
        self.assertEqual(self.policy.mode, "hold")
        self.assertLess(np.max(np.abs(np.array(held) - moved)), 0.5)
        self.policy.observe(lost, now=1000 + hand_follow.LOST_HOME_SECONDS)
        self.assertEqual(self.policy.mode, "home")


class FreshVision:
    def __init__(self, center=(100, 80)):
        self.sequence = 0
        self.center = center

    def snapshot(self):
        self.sequence += 1
        return frame(self.center, sequence=self.sequence)


class FakeRobot:
    def __init__(self):
        self.commands = []
        self.began = self.ended = False
        self.on_servo = lambda: None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.ended = True

    def joints(self):
        return list(self.commands[-1]) if self.commands else list(HOME)

    def within_limits(self, joints):
        return True

    def begin(self):
        self.began = True

    def servo(self, joints):
        self.commands.append(joints)
        self.on_servo()


class FollowWorkerTests(unittest.TestCase):
    def start(self, folder, robot, vision=None):
        path = Path(folder) / "profile.json"
        path.write_text(json.dumps(hand_profile()))
        follower = HandFollower(vision or FreshVision(), path, lambda: robot)
        return follower, follower.start()

    def test_stop_returns_to_ready_pose(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
        ):
            robot = FakeRobot()
            follower = None

            def stop_later():
                if len(robot.commands) == 60:
                    follower.stop()

            robot.on_servo = stop_later
            follower, state = self.start(folder, robot)
            with self.assertRaises(ValueError):
                follower.heartbeat("wrong-token")
            follower.heartbeat(state["token"])
            follower.worker.join(15)
            self.assertFalse(follower.worker.is_alive())
            self.assertTrue(robot.began and robot.ended)
            self.assertNotEqual(robot.commands[59], HOME)
            self.assertEqual(robot.commands[-1], HOME)
            self.assertIn("ready pose", follower.snapshot()["message"])

    def test_missing_heartbeat_ends_and_returns(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
            patch("labdeck.hand_follow.HEARTBEAT_TIMEOUT", 0.2),
        ):
            robot = FakeRobot()
            follower, _ = self.start(folder, robot)
            follower.worker.join(15)
            self.assertFalse(follower.worker.is_alive())
            self.assertEqual(robot.commands[-1], HOME)
            self.assertIn("heartbeat lost", follower.snapshot()["message"])

    def test_far_from_anchor_refuses_before_servo(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("labdeck.hand_follow.ROOT", Path(folder)),
        ):
            robot = FakeRobot()
            robot.joints = lambda: [30, -10, 45, -60, -60, 60]
            follower, _ = self.start(folder, robot)
            follower.worker.join(5)
            self.assertFalse(robot.began)
            self.assertIn("recalibrate", follower.snapshot()["message"])


if __name__ == "__main__":
    unittest.main()
