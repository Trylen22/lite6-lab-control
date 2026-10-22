# Lite 6 Lab Deck

A classroom-friendly vision and robotics workspace for the **UFACTORY Lite 6** and **Luxonis OAK-D Pro PoE**. Built independently of the JetMax project, with readable Python modules and a local browser interface.

**The browser deck remains observation-only, with no robot motion endpoint.** A separate, default-dry-run script now supports the explicitly authorized single operator-taught suction trial described below. It is not vision-guided picking.

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
| [Suction calibration plan](docs/CALIBRATION_PLAN.md) | Official reference geometry, mounting checks, and measurement procedure |
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

## Separate supervised taught trial

`scripts/taught_pick_trial.py` is separate from the classroom dashboard. It accepts explicit local approach/contact records and defaults to getter-only preflight. It permits at most a 2.1 mm vertical lift at 2 mm/s, requires the current pose and controller offsets/load to match the taught setup, requires an empty command queue and an already enabled/idle controller, and never enables, changes mode, or clears faults.

Only an explicit `--execute` runs one cycle: suction with attachment feedback → taught lift → monitored two-second hold → lower to contact → release and end the release pulse. No attachment feedback means no lift. A motion/feedback failure away from confirmed contact preserves the tool state for the operator; it does not automatically descend or release. Use the physical emergency stop for an emergency; closing the terminal/disconnecting the SDK is not a certified stop.

This script exists for the user's specifically authorized supervised trial. Do not execute it as a classroom example or reuse old coordinates. The actual local records, preflight inspection, operator presence, tool configuration, clear taught path, and unchanged block placement are prerequisites. Read the source and trial notes before use.

## Stationary suction diagnosis

`scripts/check_suction.py` inspects tool state by default. Its explicit `--pulse --pose-record <fresh-inspection.json>` option applies one two-second suction pulse at the inspected stationary pose, logs the vacuum state and all available tool inputs, then attempts release and returns the release output low. It has no arm-movement call. A changed pose, active controller, nonzero outputs, or queued commands refuses the pulse.

The SDK vacuum state means `-1 = tool off`, `0 = no pickup feedback`, and `1 = pickup feedback`. A successful output command or audible motor is not pickup confirmation. A missing seal is investigated at rest; it does not justify bypassing the attachment gate or descending to guessed coordinates. Any manual repositioning invalidates the previous taught path until new geometry is recorded.

The trial's explicit `--release-at-hover` variant performs the operator-requested small drop: after the bounded <=2.1 mm lift and monitored hold, it releases at that hover without descending into a compressed contact pose. This variant was introduced after the operator's firmer seating produced confirmed suction feedback. Default behavior still lowers to supported contact before release. The arm's reported lift and pickup feedback do not independently measure whether cup compliance absorbed travel or the object fully cleared the table; operator observation is recorded separately.
