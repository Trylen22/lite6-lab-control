"""Verify the device boundary and invalid/stale observation handling offline."""

import threading
import unittest
from labdeck.robot import RobotObserver
from labdeck.server import VisionWorkspace


class FakeArm:
    def __init__(self, stop):
        self.stop = stop
        self.connected = True
        self.calls = []

    def connect(self):
        self.calls.append("connect")

    def disconnect(self):
        self.calls.append("disconnect")

    def get_version(self):
        self.calls.append("get_version")
        return 0, "test"

    def get_state(self):
        self.calls.append("get_state")
        return 0, 5

    def get_err_warn_code(self):
        self.calls.append("get_err_warn_code")
        return 0, [0, 0]

    def get_position(self):
        self.calls.append("get_position")
        return 0, [0] * 6

    def get_servo_angle(self):
        self.calls.append("get_servo_angle")
        self.stop.set()
        return 0, [0] * 7

    def __getattr__(self, name):
        raise AssertionError(f"Unexpected robot method: {name}")


class ObservationBoundary(unittest.TestCase):
    def test_sdk_loop_only_queries_and_disconnects(self):
        stop = threading.Event()
        fake = FakeArm(stop)
        observer = RobotObserver("test", api_factory=lambda *a, **kw: fake)
        observer.run(stop)
        self.assertEqual(
            fake.calls,
            [
                "connect",
                "get_version",
                "get_state",
                "get_err_warn_code",
                "get_position",
                "get_servo_angle",
                "disconnect",
            ],
        )
        self.assertEqual(observer.snapshot()["values"]["state"], 5)

    def test_invalid_settings_do_not_mutate_and_mode_change_clears_results(self):
        vision = VisionWorkspace("http://127.0.0.1:8090")
        original = vision.settings.copy()
        for patch in (
            {"min_area": -1},
            {"confidence": float("nan")},
            {"mode": "pick"},
            {"robot_ip": "other"},
            {"min_area": True},
        ):
            with self.assertRaises(ValueError):
                vision.configure(patch)
            self.assertEqual(vision.settings, original)
        vision.detections = [{"label": "old"}]
        vision.configure({"mode": "raw"})
        self.assertEqual(vision.snapshot()["detections"], [])
        self.assertFalse(vision.snapshot()["fresh"])

    def test_old_detection_is_not_served_as_fresh(self):
        import time

        vision = VisionWorkspace("http://127.0.0.1:8090")
        vision.updated = time.monotonic() - 10
        vision.error = ""
        vision.detections = [{"label": "old"}]
        self.assertFalse(vision.snapshot()["fresh"])
        self.assertEqual(vision.snapshot()["detections"], [])


if __name__ == "__main__":
    unittest.main()
