#!/usr/bin/env python3
"""Start the deck and, only if needed, its single camera producer.

Process ownership is explicit: Ctrl+C stops children this launcher created.
An already-running camera producer is reused and is not stopped on exit.
"""

import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def camera_status():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:8090/health", timeout=1) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # A 503 means the existing producer is present but its frames are stale.
        if error.code == 503:
            raise RuntimeError(
                "Camera producer is running but not fresh; inspect its terminal"
            ) from error
        raise
    except urllib.error.URLError:
        return None


def main():
    config_path = ROOT / "local/lab.toml"
    config = tomllib.loads(config_path.read_text())
    camera_ip = config["camera"]["ip"]
    if not camera_ip or not config["robot"]["ip"]:
        raise SystemExit(
            "Record confirmed camera and robot addresses in local/lab.toml first"
        )
    children = []

    # A signal interrupts the wait and enters finally, rather than leaving an
    # orphan camera process that could prevent the next student from connecting.
    def interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        existing = camera_status()
        if existing is None:
            camera = subprocess.Popen(
                [sys.executable, "scripts/camera_preview.py", "--ip", camera_ip],
                cwd=ROOT,
            )
            children.append(camera)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if camera.poll() is not None:
                    raise RuntimeError("Camera producer exited; inspect its output")
                try:
                    status = camera_status()
                except RuntimeError:
                    status = None  # Newly started producer may still be booting.
                if status and status.get("fresh"):
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError(
                    "Camera did not deliver a fresh frame within 60 seconds"
                )
        else:
            print(
                "Reusing existing camera producer; this launcher does not own it.",
                flush=True,
            )
        deck = subprocess.Popen(
            [sys.executable, "-m", "labdeck.server", "--config", str(config_path)],
            cwd=ROOT,
        )
        children.append(deck)
        while deck.poll() is None:
            if len(children) == 2 and children[0].poll() is not None:
                raise RuntimeError("Camera producer stopped; shutting down the deck")
            time.sleep(0.5)
        if deck.returncode:
            raise RuntimeError(f"Deck exited with status {deck.returncode}")
    except KeyboardInterrupt:
        print("\nStopping processes owned by this launcher.", flush=True)
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
