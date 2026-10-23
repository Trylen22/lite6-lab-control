"""HTTP classroom dashboard with two independent observation workers.

Camera ownership stays in camera_preview.py. This service reads that producer's
fresh JPEGs over loopback, so we never open the OAK device twice. RobotObserver
only reads telemetry. Explicit same-origin pickup requests dispatch a separate
single-cycle worker; telemetry and page loads never trigger motion.
"""

import argparse
import json
from pathlib import Path
import signal
import threading
import time
import tomllib
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

import cv2
import numpy as np
from labdeck.color import PRESETS, detect_color, annotate
from labdeck.robot import RobotObserver
from labdeck.yolo import YoloDetector
from labdeck.display import upright, upright_detections
from labdeck.hands import HandDetector, draw_hands, MODEL as HAND_MODEL
from labdeck.hand_follow import HandFollower
from labdeck.start_pose import StartPoseMover
from labdeck.jobs import JobManager
from labdeck.automatic_pick import load_profile, PROFILE

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "local/models/yolox_nano.onnx"


class VisionWorkspace:
    """One worker processes the newest image, without accumulating a frame queue."""

    def __init__(self, camera_url):
        self.camera_url = camera_url.rstrip("/")
        self.condition = threading.Condition()
        self.settings = {
            "mode": "color",
            "preset": "green",
            # The green marker dot is ~600-650 px² at camera height.
            "min_area": 300,
            "confidence": 0.4,
        }
        self.revision = 0
        self.sequence = 0
        self.updated = 0.0
        self.detections = []
        self.images = {}
        self.error = "Waiting for a fresh camera image"
        self.processing_ms = 0
        self.fps = 0
        self.yolo = None
        self.hands = None
        self.source = {}

    def configure(self, patch):
        """Validate a full change before replacing state; invalid requests do nothing."""
        if not isinstance(patch, dict) or set(patch) - set(self.settings):
            raise ValueError("Unknown vision setting")
        with self.condition:
            new = {**self.settings, **patch}
            if (
                new["mode"] not in ("raw", "color", "yolo", "hands")
                or new["preset"] not in PRESETS
            ):
                raise ValueError("Choose a supported mode and color preset")
            if type(new["min_area"]) is not int or not 100 <= new["min_area"] <= 10000:
                raise ValueError(
                    "Minimum area must be an integer from 100 to 10000 pixels"
                )
            if (
                type(new["confidence"]) not in (int, float)
                or not 0.1 <= new["confidence"] <= 0.95
            ):
                raise ValueError("Confidence must be between 0.10 and 0.95")
            if new["mode"] == "yolo" and not MODEL.is_file():
                raise ValueError("Download the YOLO model before selecting this mode")
            if new["mode"] == "hands" and not HAND_MODEL.is_file():
                raise ValueError("Download the hand model before selecting this mode")
            self.settings = new
            self.revision += 1
            # Clear previous results at a mode change. A green box must never be
            # presented as a neural prediction while the next frame is processing.
            self.detections = []
            self.images = {}
            self.updated = 0
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            age = time.monotonic() - self.updated if self.updated else None
            fresh = age is not None and age < 3 and not self.error
            return {
                "fresh": fresh,
                "age_seconds": round(age, 2) if age is not None else None,
                "sequence": self.sequence,
                "settings": self.settings.copy(),
                "detections": self.detections if fresh else [],
                "error": self.error,
                "processing_ms": round(self.processing_ms, 1),
                "fps": round(self.fps, 1),
                "model_available": MODEL.is_file(),
                "hand_model_available": HAND_MODEL.is_file(),
                "source": self.source.copy(),
                "updated_monotonic": self.updated,
                "resolution": [640, 400],
                "hsv_ranges": PRESETS[self.settings["preset"]],
            }

    def run(self, stop):
        # Skip proxy environment settings: our upstream is always the configured
        # loopback camera producer, never a third-party video service.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        previous = time.monotonic()
        while not stop.is_set():
            with self.condition:
                settings, revision = self.settings.copy(), self.revision
            try:
                source = {}
                if settings["mode"] == "hands":
                    # Atomic frame + provenance lets the follow controller reject
                    # producer restarts, repeated frames and stale source pixels.
                    import base64

                    with opener.open(
                        self.camera_url + "/observation.json", timeout=2
                    ) as response:
                        packet = json.load(response)
                    raw = base64.b64decode(packet["jpeg_base64"])
                    source = {
                        key: packet[key]
                        for key in ("session", "sequence", "received_monotonic")
                    }
                    if (
                        not packet["fresh"]
                        or time.monotonic() - source["received_monotonic"] > 0.5
                    ):
                        raise ValueError("Hand source frame is stale")
                else:
                    with opener.open(
                        self.camera_url + "/snapshot.jpg", timeout=2
                    ) as response:
                        raw = response.read(2_000_000)
                image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError("Camera producer returned an invalid image")
                started = time.monotonic()
                mask = None
                detections = []
                if settings["mode"] == "color":
                    detections, mask = detect_color(
                        image, settings["preset"], settings["min_area"]
                    )
                elif settings["mode"] == "yolo":
                    if self.yolo is None:
                        self.yolo = YoloDetector(MODEL)
                    detections = self.yolo.detect(image, settings["confidence"])
                elif settings["mode"] == "hands":
                    if self.hands is None:
                        self.hands = HandDetector()
                    detections = self.hands.detect(image)
                display_image = upright(image)
                rendered = (
                    annotate(
                        display_image,
                        upright_detections(detections, image.shape[1], image.shape[0]),
                    )
                    if settings["mode"] in ("color", "yolo")
                    else display_image
                )
                if settings["mode"] == "hands":
                    rendered = draw_hands(image, detections)
                _, encoded = cv2.imencode(
                    ".jpg", rendered, [cv2.IMWRITE_JPEG_QUALITY, 85]
                )
                _, raw_display = cv2.imencode(".jpg", display_image)
                images = {"annotated": encoded.tobytes(), "raw": raw_display.tobytes()}
                if mask is not None:
                    _, encoded_mask = cv2.imencode(".jpg", upright(mask))
                    images["mask"] = encoded_mask.tobytes()
                now = time.monotonic()
                with self.condition:
                    if revision == self.revision:
                        self.source = source
                        self.images = images
                        self.detections = detections
                        self.sequence += 1
                        self.updated = now
                        self.error = ""
                        self.processing_ms = (now - started) * 1000
                        self.fps = 1 / max(0.001, now - previous)
                        self.condition.notify_all()
                previous = now
            except Exception as exc:
                with self.condition:
                    self.error = str(exc)
                    self.images = {}
                    self.detections = []
                    self.condition.notify_all()
                stop.wait(0.7)
            # A modest rate leaves CPU headroom for telemetry and teaching tools.
            stop.wait(0.10)


def make_handler(vision, robot, stop, jobs=None, follower=None, mover=None):
    dispatch_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_body(self, code, data, content_type="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, code, value):
            self.send_body(code, json.dumps(value, allow_nan=False).encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/assets/style.css": ("style.css", "text/css"),
                "/assets/app.js": ("app.js", "text/javascript"),
            }
            if path in assets:
                filename, content_type = assets[path]
                self.send_body(
                    200, (ROOT / "assets" / filename).read_bytes(), content_type
                )
            elif path == "/api/calibration":
                # Read-only teaching data. A recorded fit is NOT a live motion
                # authorization; the standalone controller rechecks all context.
                try:
                    model_path = ROOT / "local/calibration/green.json"
                    if PROFILE.exists():
                        profile = load_profile()
                        model = {
                            "aim_px": profile["cup_aim_px"],
                            "jacobian_px_per_mm": profile["jacobian_px_per_mm"],
                            "max_residual_px": profile["validation"][
                                "max_fit_residual_px"
                            ],
                            "condition": profile["validation"]["condition"],
                            "resolution": profile["resolution"],
                            "captured_utc": profile["calibrated_utc"],
                            "status": "tabletop_profile",
                            "pickup_validated": True,
                        }
                    elif model_path.exists():
                        model = json.loads(model_path.read_text())
                    else:
                        relocation = json.loads(
                            (ROOT / "local/calibration/relocation.json").read_text()
                        )
                        if relocation["status"] != "awaiting_operator_block_placement":
                            raise ValueError("No stationary placement guide")
                        # Fixed camera-to-cup geometry preserves this image guide
                        # during pure XY translation. It is NOT a renewed XY fit
                        # or a taught contact at the relocated pickup position.
                        model = {
                            **relocation["original_model"],
                            "status": "placement_guide_only",
                            "pickup_validated": False,
                        }
                    self.send_json(
                        200,
                        {
                            key: model[key]
                            for key in (
                                "aim_px",
                                "jacobian_px_per_mm",
                                "max_residual_px",
                                "condition",
                                "resolution",
                                "captured_utc",
                                "status",
                                "pickup_validated",
                            )
                        },
                    )
                except (OSError, ValueError, KeyError):
                    self.send_json(
                        200, {"status": "not_calibrated", "pickup_validated": False}
                    )
            elif path == "/api/status":
                vision_state = vision.snapshot()
                robot_state = robot.snapshot()
                job = (
                    jobs.snapshot()
                    if jobs
                    else {
                        "state": "unavailable",
                        "phase": "unavailable",
                        "message": "Pickup worker unavailable",
                    }
                )
                follow_state = (
                    follower.snapshot()
                    if follower
                    else {"state": "unavailable", "message": "Following unavailable"}
                )
                follow_ready, follow_reason = (
                    follower.readiness(robot_state)
                    if follower
                    else (False, "Following unavailable")
                )
                ready, reason = (
                    jobs.readiness(vision_state, robot_state)
                    if jobs
                    else (False, "Pickup worker unavailable")
                )
                transfer = (
                    mover.snapshot()
                    if mover
                    else {"state": "unavailable", "task": None, "message": ""}
                )
                moving = transfer["state"] == "running"
                self.send_json(
                    200,
                    {
                        "vision": vision_state,
                        "robot": robot_state,
                        "motion_available": jobs is not None,
                        "job": job,
                        "follow": follow_state,
                        "transfer": transfer,
                        "follow_ready": {
                            "ready": follow_ready
                            and job["state"] != "running"
                            and not moving,
                            "reason": follow_reason,
                        },
                        "pickup": {
                            "ready": ready
                            and job["state"] != "running"
                            and follow_state["state"] != "running"
                            and not moving,
                            "reason": reason,
                        },
                        "phase": "Green pickup workspace",
                    },
                )
            elif path == "/stream.mjpg":
                view = parse_qs(urlsplit(self.path).query).get("view", ["annotated"])[0]
                if view not in ("annotated", "raw", "mask"):
                    self.send_json(400, {"error": "Unknown view"})
                    return
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                sequence = -1
                try:
                    while not stop.is_set():
                        with vision.condition:
                            vision.condition.wait_for(
                                lambda: vision.sequence != sequence or stop.is_set(),
                                timeout=1,
                            )
                            current = vision.sequence
                            jpeg = vision.images.get(view)
                            fresh = (
                                vision.updated and time.monotonic() - vision.updated < 3
                            )
                        if stop.is_set():
                            break
                        if not fresh or jpeg is None or current == sequence:
                            # Keep the connection open during a brief mode change.
                            stop.wait(0.1)
                            continue
                        sequence = current
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(jpeg)).encode()
                            + b"\r\n\r\n"
                            + jpeg
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_json(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            # Separate host-only settings from the explicit one-cycle action.
            # There are no arbitrary coordinates, reset/enable or raw SDK routes.
            if self.path not in (
                "/api/vision",
                "/api/pick-place",
                "/api/follow/start",
                "/api/follow/stop",
                "/api/follow/heartbeat",
                "/api/go-start",
            ):
                self.send_json(
                    404, {"error": "No such action; robot commands are unavailable"}
                )
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.send_json(403, {"error": "Same-origin requests required"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    raise ValueError("Expected a small JSON settings object")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Content-Type must be application/json")
                patch = json.loads(self.rfile.read(size))
                if self.path == "/api/go-start":
                    # Only the two stored demo start poses; no coordinates.
                    if (
                        self.headers.get("X-Labdeck-Action") != "go-start"
                        or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    ):
                        self.send_json(403, {"error": "Use the local demo tabs"})
                        return
                    if mover is None:
                        raise ValueError("Start-pose moves unavailable")
                    if not isinstance(patch, dict) or set(patch) != {"task"}:
                        raise ValueError("Expected a demo task")
                    if patch["task"] not in ("pickup", "hand"):
                        raise ValueError("Unknown demo task")
                    try:
                        with dispatch_lock:
                            if jobs and jobs.snapshot()["state"] == "running":
                                raise RuntimeError("Pickup cycle active")
                            if follower and follower.snapshot()["state"] == "running":
                                raise RuntimeError("Stop hand following first")
                            state = mover.start(patch["task"])
                    except RuntimeError as exc:
                        self.send_json(409, {"error": str(exc)})
                        return
                    self.send_json(202, state)
                    return
                if self.path.startswith("/api/follow/"):
                    if (
                        self.headers.get("X-Labdeck-Action") != "hand-follow"
                        or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    ):
                        self.send_json(403, {"error": "Use local follow controls"})
                        return
                    if follower is None:
                        raise ValueError("Following unavailable")
                    action = self.path.rsplit("/", 1)[-1]
                    if action == "heartbeat":
                        if not isinstance(patch, dict) or set(patch) != {"token"}:
                            raise ValueError("Expected follow session token")
                        state = follower.heartbeat(patch["token"])
                    else:
                        if patch != {}:
                            raise ValueError("Follow controls accept no coordinates")
                        if action == "stop":
                            state = follower.stop()
                        else:
                            with dispatch_lock:
                                if jobs and jobs.snapshot()["state"] == "running":
                                    raise ValueError("Pickup cycle active")
                                if mover and mover.running():
                                    raise ValueError("Arm is moving to a start pose")
                                ready, reason = follower.readiness(robot.snapshot())
                                if not ready:
                                    raise ValueError(reason)
                                state = follower.start()
                    self.send_json(200, state)
                    return
                if self.path == "/api/pick-place":
                    # Custom header forces a browser cross-origin preflight;
                    # this loopback server supplies no permissive CORS response.
                    if (
                        self.headers.get("X-Labdeck-Action") != "pick-place"
                        or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    ):
                        self.send_json(
                            403, {"error": "Use the local Pick & Place button"}
                        )
                        return
                    # Only a named, taught destination; never coordinates.
                    if patch not in ({}, {"destination": "shelf"}):
                        raise ValueError("Pickup accepts no coordinates or settings")
                    if jobs is None:
                        raise ValueError("Pickup worker unavailable")
                    try:
                        with dispatch_lock:
                            if follower and follower.snapshot()["state"] == "running":
                                raise RuntimeError("Stop hand following before pickup")
                            if mover and mover.running():
                                raise RuntimeError("Arm is moving to a start pose")
                            job = jobs.start(
                                vision.snapshot(),
                                robot.snapshot(),
                                patch.get("destination", "table"),
                            )
                    except RuntimeError as exc:
                        self.send_json(409, {"error": str(exc)})
                        return
                    self.send_json(202, job)
                else:
                    vision.configure(patch)
                    if follower and vision.snapshot()["settings"]["mode"] != "hands":
                        follower.stop()
                    self.send_json(200, vision.snapshot())
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "local/lab.toml")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    config = tomllib.loads(args.config.read_text())
    robot_ip = config["robot"]["ip"]
    if not robot_ip:
        parser.error("Record the confirmed robot IP in local/lab.toml first")
    # The upstream is loopback-only by design, so input from a settings request
    # cannot redirect the server into another lab device or a public service.
    vision = VisionWorkspace("http://127.0.0.1:8090")
    robot = RobotObserver(robot_ip)
    stop = threading.Event()
    jobs = JobManager()
    follower = HandFollower(vision)
    mover = StartPoseMover()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(vision, robot, stop, jobs, follower, mover),
    )
    workers = [
        threading.Thread(target=vision.run, args=(stop,), daemon=True),
        threading.Thread(target=robot.run, args=(stop,), daemon=True),
        threading.Thread(target=server.serve_forever, daemon=True),
    ]
    for worker in workers:
        worker.start()
    print(
        f"Lite 6 Lab Deck: http://127.0.0.1:{args.port}/ — explicit one-cycle pickup",
        flush=True,
    )
    try:
        stop.wait()
    finally:
        follower.join()
        mover.wait()
        jobs.wait_for_completion()
        stop.set()
        with vision.condition:
            vision.condition.notify_all()
        server.shutdown()
        server.server_close()
        for worker in workers:
            worker.join(timeout=4)


if __name__ == "__main__":
    main()
