# Lite 6 Lab Deck

A classroom-friendly vision and robotics workspace for the **UFACTORY Lite 6** and **Luxonis OAK-D Pro PoE**. Built independently of the JetMax project, with readable Python modules and a local browser interface.

**Current phase: observation and vision. No robot movement, enabling, reset, or gripper commands are implemented.**

## What works now

- Local dashboard at **http://127.0.0.1:8100/** with vision workspace, robot telemetry, learning path, and system notes.
- Live color camera; raw, annotated, and HSV mask views.
- OpenCV color detection with green/cyan, red, blue, and yellow presets and an adjustable minimum region area.
- **YOLOX-Nano** on the laptop CPU through OpenCV DNN. This is a small pretrained YOLO-family model, not a model currently running on the camera. Its 80 COCO classes cover everyday objects, not custom lab parts.
- Read-only UFACTORY SDK telemetry: firmware, controller state code, errors/warnings, tool pose, and six joint angles.
- Explicit freshness indicators: a lost camera or robot connection is reported rather than treated as a valid observation.

All detection coordinates are **image pixels**. There is no camera-to-robot calibration or automatic picking yet.

## Quick start on the laptop

Validated baseline: **Linux x86_64, Python 3.12**. The original Jetson Nano has not been validated with these dependencies.

```bash
cd /path/to/LITE6
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-deck.txt
mkdir -p local
cp --no-clobber config/lab.example.toml local/lab.toml
```

Edit `local/lab.toml` with the **confirmed** robot and camera addresses. Do not overwrite existing local configuration. Actual device addresses and credentials stay out of Git.

```bash
# Download the official 3.5 MB YOLOX-Nano ONNX release and check its hash.
.venv/bin/python scripts/download_yolo.py

# Launch the camera producer if needed, then the dashboard.
./run.sh
```

Open **http://127.0.0.1:8100/** in a browser on this laptop. Stop the launcher with **Ctrl+C**. Settings return to defaults on a new deck process; changing a UI vision setting never changes robot settings.

The launcher reuses an existing camera producer on port 8090. It stops only child processes it started. To run the parts separately:

```bash
# Terminal 1: only one process should own the camera.
.venv/bin/python scripts/camera_preview.py --ip <confirmed-camera-IP>

# Terminal 2: consumes fresh JPEGs from Terminal 1 and reads arm telemetry.
.venv/bin/python -m labdeck.server
```

If the deck is already running, open its URL rather than launching a second copy. Loopback binding means it is accessible only from the host laptop; network sharing/remote access is a later setup step.

## Start reading here

| File | What students learn |
|---|---|
| [Classroom guide](docs/CLASSROOM_GUIDE.md) | Guided exercises and questions |
| [Architecture](docs/ARCHITECTURE.md) | Data flow, processes, units, failure handling |
| [Roadmap](docs/ROADMAP.md) | Staged plan through calibration and pick-and-place |
| [Lab setup](docs/LAB_SETUP.md) | Network and hardware preparation |
| [Current status](docs/STATUS.md) | Verified behavior and remaining limits |
| [Session history](docs/SESSION_LOG.md) | How we reached the current setup |

## Source map

```text
assets/                     Browser HTML, readable CSS, and commented JavaScript
labdeck/
  color.py                  HSV → mask → contours → pixel candidates
  yolo.py                   CPU model preprocessing, inference, and box decoding
  robot.py                  Small read-only boundary around the UFACTORY SDK
  server.py                 HTTP endpoints and independent observation workers
scripts/
  camera_preview.py         Owns the OAK pipeline; serves fresh local frames
  discover_camera.py        Enumerates OAK devices without starting a stream
  download_yolo.py          Explicit model download with a pinned checksum
  host_inventory.sh         Read-only inspection of the local host
  run_lab.py                Starts/reuses processes and handles shutdown
config/lab.example.toml      Sanitized device configuration template
tests/                      Offline vision geometry and observation-boundary checks
local/                      Ignored actual configuration, model, and diagnostics
```

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check assets/app.js
# Optional formatter/linter (install requirements-dev.txt first):
.venv/bin/ruff check labdeck scripts tests
.venv/bin/ruff format --check labdeck scripts tests
bash -n run.sh
.venv/bin/python -m pip check
```

Offline tests cover colored regions/noise, red hue wraparound, pixel-coordinate geometry, YOLO duplicate suppression, invalid settings, stale results, and the robot getter-only boundary. Hardware validation is recorded separately; passing an offline test does not establish physical readiness.

## Keeping the project clean

Use this repo for Lite 6/OAK work and the separate JetMax repo for JetMax work. Keep machine addresses, credentials, model weights, images, recordings, and logs under ignored `local/`, `data/`, or another ignored directory. Commit source, sanitized examples, explanatory notes, and validation results after each coherent milestone, then push to this project's private remote.

The model is downloaded explicitly rather than committed or fetched silently at startup. See [third-party references](docs/THIRD_PARTY.md) for provenance and licenses.
