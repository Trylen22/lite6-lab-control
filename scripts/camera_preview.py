#!/usr/bin/env python3
"""Stream color video to localhost. No robot control or persistent camera writes."""

import argparse
import base64
import json
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import depthai as dai


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="Confirmed OAK camera address")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    stop = threading.Event()
    condition = threading.Condition()
    latest = {"jpeg": None, "frames": 0, "time": 0.0}
    session_id = uuid.uuid4().hex
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/":
                body = b"""<!doctype html><html><head><title>OAK color preview</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#111;color:#eee;font:18px sans-serif;margin:24px}
img{max-width:100%;border:1px solid #555}a{color:#9cf}</style></head>
<body><h1>OAK live color preview</h1><p>640 x 400, 15 FPS requested.</p>
<img src="/stream.mjpg" alt="Live camera feed">
<p id="status">Connecting...</p><script>
setInterval(async()=>{try{const r=await fetch('/health');const s=await r.json();
document.getElementById('status').textContent=s.fresh?
'Live | frames received: '+s.frames:'Feed unavailable or stale';}
catch(e){document.getElementById('status').textContent='Preview server disconnected';}},1000);
</script></body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path in ("/health", "/snapshot.jpg", "/observation.json"):
                with condition:
                    frame = latest.copy()
                age = time.monotonic() - frame["time"]
                fresh = frame["jpeg"] is not None and age < 3 and not stop.is_set()
                if self.path == "/health":
                    body = json.dumps(
                        {
                            "fresh": fresh,
                            "frames": frame["frames"],
                            "age_seconds": round(age, 3),
                        }
                    ).encode()
                    content_type = "application/json"
                elif self.path == "/observation.json":
                    # Metadata and pixels come from ONE locked copy. A consumer
                    # can reject duplicate frames and frames from an old process.
                    body = json.dumps(
                        {
                            "session": session_id,
                            "sequence": frame["frames"],
                            "received_monotonic": frame["time"],
                            "age_seconds": age,
                            "fresh": fresh,
                            "jpeg_base64": base64.b64encode(frame["jpeg"]).decode()
                            if fresh
                            else None,
                        }
                    ).encode()
                    content_type = "application/json"
                else:
                    body = frame["jpeg"] if fresh else b"No fresh frame"
                    content_type = "image/jpeg" if fresh else "text/plain"
                self.send_response(200 if fresh else 503)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                previous = -1
                try:
                    while not stop.is_set():
                        with condition:
                            condition.wait_for(
                                lambda: latest["frames"] != previous or stop.is_set(), 1
                            )
                            frame = latest.copy()
                        if stop.is_set() or time.monotonic() - frame["time"] > 3:
                            break
                        if frame["frames"] == previous or frame["jpeg"] is None:
                            continue
                        previous = frame["frames"]
                        data = frame["jpeg"]
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(data)).encode()
                            + b"\r\n\r\n"
                            + data
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

    # Bind only to loopback; fail before connecting if the requested port is busy.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Preview URL: http://127.0.0.1:{args.port}/", flush=True)
    try:
        with dai.Device(dai.DeviceInfo(args.ip)) as device:
            print("Device:", device.getDeviceName(), flush=True)
            for feature in device.getConnectedCameraFeatures():
                print(
                    "Sensor:",
                    feature.socket,
                    feature.sensorName,
                    feature.width,
                    feature.height,
                    flush=True,
                )
            with dai.Pipeline(device) as pipeline:
                camera = pipeline.create(dai.node.Camera).build(
                    dai.CameraBoardSocket.CAM_A
                )
                queue = camera.requestOutput(
                    (640, 400), type=dai.ImgFrame.Type.BGR888p, fps=15
                ).createOutputQueue(maxSize=2, blocking=False)
                pipeline.start()
                last_received = time.monotonic()
                while pipeline.isRunning() and not stop.is_set():
                    message = queue.tryGet()
                    if message is None:
                        if time.monotonic() - last_received > 20:
                            raise RuntimeError(
                                "No camera frames received for 20 seconds"
                            )
                        stop.wait(0.01)
                        continue
                    last_received = time.monotonic()
                    ok, encoded = cv2.imencode(
                        ".jpg", message.getCvFrame(), [cv2.IMWRITE_JPEG_QUALITY, 80]
                    )
                    if not ok:
                        raise RuntimeError("JPEG encoding failed")
                    with condition:
                        latest.update(
                            jpeg=encoded.tobytes(),
                            time=last_received,
                            frames=latest["frames"] + 1,
                        )
                        condition.notify_all()
                    if latest["frames"] == 1:
                        print("First color frame received", flush=True)
    finally:
        stop.set()
        with condition:
            condition.notify_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
