"""Offline lessons: use synthetic pixels to verify meaningful detector behavior."""

import unittest
import cv2
import numpy as np
from labdeck.color import detect_color
from labdeck.yolo import decode


class ColorLessons(unittest.TestCase):
    def test_green_block_centroid_and_small_noise_rejection(self):
        image = np.zeros((240, 320, 3), np.uint8)
        cv2.rectangle(image, (80, 60), (160, 140), (0, 255, 0), -1)
        cv2.rectangle(image, (10, 10), (15, 15), (0, 255, 0), -1)
        results, mask = detect_color(image)
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["center"][0], 120, delta=1)
        self.assertAlmostEqual(results[0]["center"][1], 100, delta=1)
        self.assertNotIn("arm_dx_mm", results[0])
        self.assertEqual(mask.shape, image.shape[:2])

    def test_red_wraparound_and_strip_rejection(self):
        hsv = np.zeros((220, 320, 3), np.uint8)
        hsv[30:90, 30:90] = (2, 255, 220)
        hsv[110:170, 110:170] = (177, 255, 220)
        hsv[10:210, 260:270] = (2, 255, 220)
        results, _ = detect_color(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR), "red")
        self.assertEqual(len(results), 2)

    def test_white_background_is_not_green(self):
        results, _ = detect_color(np.full((240, 320, 3), 240, np.uint8))
        self.assertEqual(results, [])


class YoloGeometry(unittest.TestCase):
    def test_grid_decode_and_duplicate_suppression(self):
        output = np.zeros((1, 3549, 85), np.float32)
        # Two neighboring grid cells predict the same 40x40 box at (80,80).
        for index, offset in ((0, 10), (1, 9)):
            output[0, index, :4] = [offset, 10, np.log(5), np.log(5)]
            output[0, index, 4] = 0.9
            output[0, index, 7] = 0.9  # COCO index 2 = car
        results = decode(output, 1, 416, 416, 0.4)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["label"], "car")
        self.assertEqual(results[0]["bbox"], [60, 60, 40, 40])
        self.assertAlmostEqual(results[0]["confidence"], 0.81, places=2)

    def test_incompatible_export_is_rejected(self):
        with self.assertRaises(ValueError):
            decode(np.zeros((1, 8400, 84), np.float32), 1, 416, 416)


if __name__ == "__main__":
    unittest.main()
