"""Offline frame sequences exercise waiting without authorizing stale movement."""

import base64
from contextlib import ExitStack
import io
import itertools
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from labdeck.green_calibrate import observe


class FreshObservationTests(unittest.TestCase):
    def run_frames(self, centers, sequences=None, sessions=None, fresh=True):
        encoded = cv2.imencode(".jpg", np.zeros((100, 100, 3), np.uint8))[1].tobytes()
        sequences = sequences or list(range(1, len(centers) + 1))
        sessions = sessions or ["camera-session"] * len(sequences)
        responses = [
            {
                "session": session,
                "sequence": seq,
                "received_monotonic": 0.9,
                "age_seconds": 0.1,
                "fresh": fresh,
                "jpeg_base64": base64.b64encode(encoded).decode(),
            }
            for session, seq in zip(sessions, sequences)
        ]

        def response(*args, **kwargs):
            return io.BytesIO(json.dumps(responses.pop(0)).encode())

        detections = []
        for center in centers:
            candidates = (
                [] if center is None else [{"center": center, "bbox": [40, 40, 10, 10]}]
            )
            if center == "ambiguous":
                candidates = [
                    {"center": [45, 45], "bbox": [40, 40, 10, 10]},
                    {"center": [65, 65], "bbox": [60, 60, 10, 10]},
                ]
            detections.append((candidates, None))
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "labdeck.green_calibrate.time.monotonic",
                    side_effect=itertools.chain([0, 0], itertools.repeat(1)),
                )
            )
            stack.enter_context(patch("labdeck.green_calibrate.time.sleep"))
            fetch = stack.enter_context(
                patch(
                    "labdeck.green_calibrate.urllib.request.urlopen",
                    side_effect=response,
                )
            )
            detector = stack.enter_context(
                patch("labdeck.green_calibrate.detect_color", side_effect=detections)
            )
            result = observe()
            return result, fetch.call_count, detector.call_count

    def test_missing_detection_resets_consecutive_stable_window(self):
        result, _, _ = self.run_frames([[40, 40], None, [50, 50], [50, 50], [50, 50]])
        self.assertEqual(result["center_px"], [50, 50])
        self.assertEqual(result["sequence"], 5)

    def test_unstable_window_waits_for_three_stable_centers(self):
        result, _, _ = self.run_frames([[40, 40], [50, 50], [50, 50], [50, 50]])
        self.assertEqual(result["center_px"], [50, 50])
        self.assertEqual(result["sequence"], 4)

    def test_duplicate_frame_does_not_count_toward_three(self):
        result, fetches, decoded = self.run_frames(
            [[50, 50]] * 3, sequences=[1, 1, 2, 3]
        )
        self.assertEqual((fetches, decoded), (4, 3))
        self.assertEqual(result["sequence"], 3)

    def test_stale_input_and_camera_restart_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Camera stale"):
            self.run_frames([[50, 50]], fresh=False)
        with self.assertRaisesRegex(RuntimeError, "Camera restarted"):
            self.run_frames([[50, 50]] * 3, sessions=["one", "two", "two"])

    def test_multiple_candidates_are_rejected_without_reacquisition(self):
        with self.assertRaisesRegex(
            RuntimeError, "Expected one green candidate, found 2"
        ):
            self.run_frames(["ambiguous"])
