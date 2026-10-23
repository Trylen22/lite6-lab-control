# Third-party components and references

## YOLOX-Nano

- Upstream: https://github.com/Megvii-BaseDetection/YOLOX
- Official model release: `0.1.1rc0/yolox_nano.onnx` (416 × 416, COCO classes).
- Download URL: https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx
- SHA256 verified in this project: `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`.
- Upstream license: Apache-2.0; preserved in [YOLOX-LICENSE.txt](licenses/YOLOX-LICENSE.txt).

Our small OpenCV adapter explains and implements the preprocessing and raw output decoding described by the official `yolox/data/data_augment.py`, `yolox/utils/demo_utils.py`, and ONNXRuntime demo. It does not include the upstream training framework. Copyright and license for the upstream project remain with its authors.

The upstream `assets/dog.jpg` sample was downloaded to ignored `local/` for a one-time model smoke check. It is not redistributed in this repository. Offline tests use synthetic data instead.

## Hardware/software references

- UFACTORY SDK and its API definitions: https://github.com/xArm-Developer/xArm-Python-SDK
- DepthAI camera output example: https://docs.luxonis.com/software-v3/depthai/examples/camera/camera_output
- OAK PoE networking: https://docs.luxonis.com/hardware/platform/deploy/poe-deployment-guide
- Luxonis neural-network deployment: https://docs.luxonis.com/software-v3/ai-inference/conversion
- OpenCV YOLO DNN guide: https://docs.opencv.org/5.0/tutorials/dnn/dnn_yolo/dnn_yolo.html

Dependency licenses are supplied by their respective packages. Version pins document the tested laptop environment; no device firmware or SDK implementation is vendored here.

## MediaPipe hand landmarks and gestures

- Python package tested: MediaPipe 0.10.35 (local CPU inference).
- Official guide: https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python
- Model overview/card: https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index
- Pinned version 1 bundle: https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
- SHA256: `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`.

The explicit downloader checks that hash; the 8.37 MB model remains ignored
locally. The package supplies its license and the linked model documentation
provides model provenance. No webcam, microphone or remote inference service
is opened by our adapter; it consumes the existing OAK producer. OpenCV contrib
replaces the overlapping headless wheel because MediaPipe depends on contrib;
the project uses one pinned OpenCV distribution rather than both sharing cv2.
