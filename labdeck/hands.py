"""Local hand landmarks and gestures; this module has no robot dependency.

MediaPipe normalized image coordinates become pixels for rendering/centering.
Its inferred world landmarks are deliberately NOT treated as measured camera
range or robot coordinates. Palm center averages wrist and four knuckles.
"""

from pathlib import Path
import time

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parents[1] / "local/models/gesture_recognizer.task"
CONNECTIONS = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
]


class HandDetector:
    def __init__(self, path=MODEL):
        # Lazy import: color/YOLO lessons still work before hand dependencies
        # and the explicitly downloaded model have been installed.
        import mediapipe as mp
        from mediapipe.tasks.python import vision

        self.mp = mp
        self.last_timestamp = 0
        options = vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.65,
            min_tracking_confidence=0.65,
        )
        self.engine = vision.GestureRecognizer.create_from_options(options)

    def detect(self, bgr):
        rgb = cv2.cvtColor(cv2.rotate(bgr, cv2.ROTATE_180), cv2.COLOR_BGR2RGB)
        timestamp = max(self.last_timestamp + 1, int(time.monotonic() * 1000))
        self.last_timestamp = timestamp
        result = self.engine.recognize_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), timestamp
        )
        height, width = bgr.shape[:2]
        detections = []
        for index, landmarks in enumerate(result.hand_landmarks):
            # Infer upright, then invert that display transform before publishing
            # sensor-frame coordinates to the already calibrated controller.
            points = np.array(
                [
                    [width - 1 - p.x * width, height - 1 - p.y * height]
                    for p in landmarks
                ]
            )
            if points.shape != (21, 2) or not np.isfinite(points).all():
                continue
            center = points[[0, 5, 9, 13, 17]].mean(axis=0)
            lo, hi = points.min(axis=0), points.max(axis=0)
            gesture = result.gestures[index][0] if result.gestures[index] else None
            detections.append(
                {
                    "label": "hand",
                    "gesture": gesture.category_name if gesture else "None",
                    "confidence": float(gesture.score) if gesture else 0.0,
                    "center": center.round(1).tolist(),
                    "bbox": [
                        float(lo[0]),
                        float(lo[1]),
                        float(hi[0] - lo[0]),
                        float(hi[1] - lo[1]),
                    ],
                    "landmarks": points.round(1).tolist(),
                    "handedness": result.handedness[index][0].category_name,
                }
            )
        return detections


def draw_hands(image, detections):
    # Rotate only the rendered view. Inference/controller pixels stay in the
    # original sensor frame, so a UI convenience cannot silently invert motion.
    rendered = cv2.rotate(image, cv2.ROTATE_180)
    detections = [
        {
            **hand,
            "center": [639 - hand["center"][0], 399 - hand["center"][1]],
            "landmarks": [[639 - x, 399 - y] for x, y in hand["landmarks"]],
        }
        for hand in detections
    ]
    cv2.circle(rendered, (320, 200), 25, (255, 200, 50), 1)
    cv2.drawMarker(rendered, (320, 200), (255, 200, 50), cv2.MARKER_CROSS, 16, 1)
    for hand in detections:
        points = np.array(hand["landmarks"], dtype=int)
        for a, b in CONNECTIONS:
            cv2.line(rendered, tuple(points[a]), tuple(points[b]), (60, 210, 255), 2)
        for point in points:
            cv2.circle(rendered, tuple(point), 3, (80, 255, 130), -1)
        center = tuple(np.array(hand["center"], dtype=int))
        cv2.circle(rendered, center, 6, (255, 130, 60), -1)
        cv2.putText(
            rendered,
            hand["gesture"],
            (max(0, center[0] - 45), max(20, center[1] - 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return rendered
