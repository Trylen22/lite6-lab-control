"""Display-only 180 degree transform. Robot/inference coordinates stay native."""

import cv2


def upright(image):
    return cv2.rotate(image, cv2.ROTATE_180)


def upright_detections(detections, width, height):
    rendered = []
    for item in detections:
        copy = item.copy()
        x, y, w, h = item["bbox"]
        copy["bbox"] = [round(width - x - w), round(height - y - h), round(w), round(h)]
        if "center" in item:
            copy["center"] = [
                width - 1 - item["center"][0],
                height - 1 - item["center"][1],
            ]
        rendered.append(copy)
    return rendered
