"""Lesson 1: turn color pixels into candidate objects.

OpenCV receives BGR images. HSV separates hue (color family) from saturation
(color strength) and value (brightness), which makes thresholds easier to teach.
All measurements here are IMAGE PIXELS. Robot coordinates require calibration.
"""

import cv2
import numpy as np

# Hue is 0..179 in OpenCV, whereas saturation and value are 0..255.
# Red crosses the hue wraparound, so it needs two intervals.
PRESETS = {
    "green": [(35, 55, 55, 110, 255, 255)],  # JetMax's broad green/cyan family
    "red": [(0, 90, 65, 10, 255, 255), (170, 90, 65, 179, 255, 255)],
    "blue": [(95, 90, 55, 130, 255, 255)],
    "yellow": [(18, 90, 65, 35, 255, 255)],
}


def detect_color(bgr, preset="green", min_area=800):
    """Return JSON-friendly boxes/centroids and a cleaned binary teaching mask."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(bgr, (5, 5), 0), cv2.COLOR_BGR2HSV)
    mask = np.zeros(bgr.shape[:2], np.uint8)
    for h0, s0, v0, h1, s1, v1 in PRESETS[preset]:
        mask |= cv2.inRange(hsv, (h0, s0, v0), (h1, s1, v1))
    # Opening removes speckles; closing fills small gaps. Neither identifies
    # an object semantically: another object of the same color can still pass.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        # Retain JetMax's rejection of thin strips and fragmented shapes,
        # but deliberately omit its physical offsets and movement calibration.
        if min(rw, rh) <= 0 or hull_area <= 0:
            continue
        if (
            max(rw, rh) / min(rw, rh) > 2.2
            or area / (rw * rh) < 0.55
            or area / hull_area < 0.75
        ):
            continue
        moments = cv2.moments(contour)
        if not moments["m00"]:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        detections.append(
            {
                "label": preset,
                "bbox": [x, y, w, h],
                "center": [
                    round(moments["m10"] / moments["m00"], 1),
                    round(moments["m01"] / moments["m00"], 1),
                ],
                "area_px": round(area),
                "confidence": None,
            }
        )
    return sorted(detections, key=lambda d: d["area_px"], reverse=True)[:20], mask


def annotate(bgr, detections):
    """Draw on a COPY so the raw frame remains available for comparison."""
    out = bgr.copy()
    h, w = out.shape[:2]
    cv2.drawMarker(out, (w // 2, h // 2), (160, 160, 160), cv2.MARKER_CROSS, 20, 1)
    for item in detections:
        x, y, bw, bh = item["bbox"]
        cv2.rectangle(out, (x, y), (x + bw, y + bh), (115, 235, 75), 2)
        label = item["label"]
        if item["confidence"] is not None:
            label += f" {item['confidence']:.0%}"
        cv2.putText(
            out,
            label,
            (x, max(18, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (115, 235, 75),
            1,
        )
        if "center" in item:
            cx, cy = item["center"]
            cv2.circle(out, (round(cx), round(cy)), 4, (115, 235, 75), -1)
    return out
