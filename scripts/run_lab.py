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
    """Return the producer's health JSON, or None when nothing serves port 8090.

    A 503 means a producer is running but has no fresh frame yet (camera not
    attached or still connecting). That is a normal state, not an error.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:8090/health", timeout=1) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 503:
            return {"fresh": False}
        raise
    except urllib.error.URLError:
        return None


def load_config():
    """Prefer this station's ignored local/lab.toml; fall back to the published
    shared-station addresses so a fresh clone opens the page with no setup.

    Addresses only let the deck LOOK for devices. Motion still needs the
    validated profiles in local/ and the per-click preflight.
    """
    for path in (ROOT / "local/lab.toml", ROOT / "config/lab.station.example.toml"):
        if path.exists():
            print(f"Config: {path.relative_to(ROOT)}", flush=True)
            return path, tomllib.loads(path.read_text())
    raise SystemExit("No config found; see README.md")


def start_camera(camera_ip):
    return subprocess.Popen(
        [sys.executable, "scripts/camera_preview.py", "--ip", camera_ip],
        cwd=ROOT,
    )


def main():
    config_path, config = load_config()
    camera_ip = config["camera"]["ip"]
    if not camera_ip or not config["robot"]["ip"]:
        raise SystemExit(
            f"Record camera and robot addresses in {config_path.relative_to(ROOT)}"
        )
    children = []
    camera = None

    # A signal interrupts the wait and enters finally, rather than leaving an
    # orphan camera process that could prevent the next student from connecting.
    def interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        # The page comes up first and always. The camera producer and the
        # deck's robot observer each keep retrying in the background, so
        # plugging in the camera or arm later is all that is needed.
        if camera_status() is None:
            camera = start_camera(camera_ip)
            children.append(camera)
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
        print("Open http://127.0.0.1:8100/ (Ctrl+C to stop)", flush=True)
        next_port_check = time.monotonic() + 5
        while deck.poll() is None:
            # The producer retries a missing camera itself; it only exits on a
            # real fault (bad install, port taken). Restart it, never the deck.
            if camera is not None and camera.poll() is not None:
                print(
                    f"Camera producer exited ({camera.returncode}); restarting in 5 s",
                    flush=True,
                )
                time.sleep(5)
                children.remove(camera)
                camera = start_camera(camera_ip)
                children.insert(0, camera)
            # A reused producer belongs to someone else and may go away (for
            # example one still shutting down from the previous launch). If
            # port 8090 goes quiet, start one this launcher owns.
            elif camera is None and time.monotonic() >= next_port_check:
                next_port_check = time.monotonic() + 5
                if camera_status() is None:
                    print("Reused camera producer is gone; starting one", flush=True)
                    camera = start_camera(camera_ip)
                    children.insert(0, camera)
            time.sleep(0.5)
        if deck.returncode:
            raise RuntimeError(f"Deck exited with status {deck.returncode}")
    except KeyboardInterrupt:
        print("\nStopping processes owned by this launcher.", flush=True)
    finally:
        # A graceful launcher exit must not kill a controller mid-cycle or stop
        # its camera producer. Observe job state; this is not a robot stop API.
        if children:
            waiting = False
            while True:
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8100/api/status", timeout=1
                    ) as response:
                        active = (
                            json.load(response).get("job", {}).get("state") == "running"
                        )
                except (OSError, ValueError):
                    active = False
                if not active:
                    break
                if not waiting:
                    print(
                        "Waiting for the active pickup before shutdown; physical E-stop stops the robot immediately.",
                        flush=True,
                    )
                    waiting = True
                time.sleep(0.5)
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
