"""New wrist orientation needs its own plane; display inversion never alters it."""

import unittest
import numpy as np
from labdeck.display import upright, upright_detections
from labdeck.hand_calibrate import SceneFlow
from labdeck.hand_space import check_hand_pose


class HandSpaceTests(unittest.TestCase):
    def test_camera_display_rotates_pixels_and_overlay_without_mutating_sensor_result(
        self,
    ):
        image = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        self.assertTrue(np.array_equal(upright(image)[0, 0], image[-1, -1]))
        detection = {"bbox": [10, 20, 30, 40], "center": [25, 40]}
        shown = upright_detections([detection], 640, 400)[0]
        self.assertEqual(shown["bbox"], [600, 340, 30, 40])
        self.assertEqual(shown["center"], [614, 359])
        self.assertEqual(detection["center"], [25, 40])

    def test_wrist_limits_keep_base_shoulder_and_roll_fixed(self):
        profile = {
            "anchor_joints_deg": [0, -10, 45, -60, -60, 60],
            "joint_axes": [3, 4],
            "joint_min_deg": [-65, -65],
            "joint_max_deg": [-55, -55],
        }
        check_hand_pose([0, -10, 45, -61, -58, 60], profile)
        with self.assertRaises(RuntimeError):
            check_hand_pose([1, -10, 45, -61, -58, 60], profile)
        with self.assertRaises(RuntimeError):
            check_hand_pose([0, -10, 45, -66, -58, 60], profile)

    def test_scene_flow_recovers_a_small_known_shift(self):
        import cv2

        rng = np.random.default_rng(7)
        image = rng.integers(0, 255, (200, 320), dtype=np.uint8)
        image = cv2.GaussianBlur(image, (3, 3), 0)
        translated = cv2.warpAffine(
            image, np.float32([[1, 0, 1.5], [0, 1, -1]]), (320, 200)
        )
        shift, inliers = SceneFlow(image).measure(translated)
        self.assertTrue(np.allclose(shift, [1.5, -1], atol=0.12))
        self.assertGreater(inliers, 25)

    def test_ceiling_roi_scale_is_not_mislabeled_as_translation(self):
        import cv2

        rng = np.random.default_rng(11)
        image = cv2.GaussianBlur(
            rng.integers(0, 255, (400, 640), dtype=np.uint8), (3, 3), 0
        )
        transform = cv2.getRotationMatrix2D((320, 200), 0, 1.003)
        scaled = cv2.warpAffine(image, transform, (640, 400))
        shift, _ = SceneFlow(image, roi=[0, 290, 640, 110]).measure(scaled)
        self.assertLess(np.linalg.norm(shift), 0.15)
