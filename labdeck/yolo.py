"""Lesson 2: small pretrained YOLO model, running on the laptop CPU.

We use the official YOLOX-Nano ONNX release with OpenCV DNN. This avoids a
large PyTorch install and makes preprocessing/decoding explicit for students.
Reference: https://github.com/Megvii-BaseDetection/YOLOX (Apache-2.0).
This COCO model recognizes 80 everyday classes; it is not trained for lab parts.
"""

from pathlib import Path
import cv2
import numpy as np

LABELS = (
    "person,bicycle,car,motorcycle,airplane,bus,train,truck,boat,traffic light,"
    "fire hydrant,stop sign,parking meter,bench,bird,cat,dog,horse,sheep,cow,"
    "elephant,bear,zebra,giraffe,backpack,umbrella,handbag,tie,suitcase,frisbee,"
    "skis,snowboard,sports ball,kite,baseball bat,baseball glove,skateboard,"
    "surfboard,tennis racket,bottle,wine glass,cup,fork,knife,spoon,bowl,banana,"
    "apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,couch,"
    "potted plant,bed,dining table,toilet,tv,laptop,mouse,remote,keyboard,"
    "cell phone,microwave,oven,toaster,sink,refrigerator,book,clock,vase,"
    "scissors,teddy bear,hair drier,toothbrush"
).split(",")


def decode(output, ratio, width, height, confidence=0.4):
    """Decode the official raw 416px model outputs into original-image boxes.

    Each prediction has center offsets, log width/height, objectness, and 80
    class probabilities. Grids at strides 8/16/32 map offsets to input pixels.
    """
    rows = output[0].copy()
    if rows.shape != (3549, 85):
        raise ValueError(
            f"Expected official YOLOX-Nano raw output (3549,85), got {rows.shape}"
        )
    grids, strides = [], []
    for stride in (8, 16, 32):
        yy, xx = np.mgrid[: 416 // stride, : 416 // stride]
        grids.append(np.stack((xx, yy), axis=-1).reshape(-1, 2))
        strides.append(np.full((xx.size, 1), stride))
    stride_values = np.concatenate(strides)
    rows[:, :2] = (rows[:, :2] + np.concatenate(grids)) * stride_values
    rows[:, 2:4] = np.exp(np.clip(rows[:, 2:4], -20, 20)) * stride_values
    scores = rows[:, 4:5] * rows[:, 5:]
    classes = scores.argmax(axis=1)
    best = scores[np.arange(len(rows)), classes]
    candidates = np.flatnonzero(best >= confidence)
    boxes, probabilities, ids = [], [], []
    for index in candidates:
        cx, cy, bw, bh = rows[index, :4] / ratio
        x0, y0 = np.clip([cx - bw / 2, cy - bh / 2], [0, 0], [width, height])
        x1, y1 = np.clip([cx + bw / 2, cy + bh / 2], [0, 0], [width, height])
        if x1 <= x0 or y1 <= y0:
            continue
        boxes.append([float(x0), float(y0), float(x1 - x0), float(y1 - y0)])
        probabilities.append(float(best[index]))
        ids.append(int(classes[index]))
    # NMS removes overlapping duplicate predictions, separately for each class.
    results = []
    for cls in sorted(set(ids)):
        members = [i for i, value in enumerate(ids) if value == cls]
        keep = cv2.dnn.NMSBoxes(
            [boxes[i] for i in members],
            [probabilities[i] for i in members],
            confidence,
            0.45,
        )
        for local_index in np.array(keep).reshape(-1):
            index = members[int(local_index)]
            results.append(
                {
                    "label": LABELS[cls],
                    "bbox": [round(v) for v in boxes[index]],
                    "confidence": round(probabilities[index], 3),
                }
            )
    return sorted(results, key=lambda item: item["confidence"], reverse=True)[:30]


class YoloDetector:
    """One worker owns this network: OpenCV Net is not shared between threads."""

    def __init__(self, model_path):
        if not Path(model_path).is_file():
            raise FileNotFoundError("YOLO model missing; run scripts/download_yolo.py")
        self.net = cv2.dnn.readNetFromONNX(str(model_path))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        # The pinned standard OpenCV wheel executes this graph on CPU by default.
        # OpenCV 5's graph engine does not support setPreferableTarget().

    def detect(self, bgr, confidence=0.4):
        height, width = bgr.shape[:2]
        ratio = min(416 / height, 416 / width)
        # Official YOLOX preprocessing: preserve aspect, pad bottom/right with
        # 114, keep BGR and 0..255 values. Do not apply another YOLO's /255 rule.
        canvas = np.full((416, 416, 3), 114, np.uint8)
        resized = cv2.resize(bgr, (int(width * ratio), int(height * ratio)))
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        blob = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], np.float32)
        self.net.setInput(blob)
        return decode(self.net.forward(), ratio, width, height, confidence)
