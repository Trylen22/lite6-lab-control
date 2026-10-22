# Lite 6 Lab Control

Separate workspace for a UFACTORY Lite 6 (label model LI10) and Luxonis OAK-D Pro PoE camera. This project is independent of `../JETMAX` and `Trylen22/jetmax-control`.

## Current status

Repository and local configuration structure are ready. No lab device has been connected, configured, calibrated, or moved by this project. Device addresses, host computer, tool, and installed software versions are not yet confirmed.

## Start here

1. Read [lab setup](docs/LAB_SETUP.md) and record observations in `local/inventory.md`.
2. Run `./scripts/host_inventory.sh` on the computer intended to host control software. This reports local system information only; it does not contact the robot or camera.
3. Copy `config/lab.example.toml` to `local/lab.toml` and fill in confirmed values. The configuration is a planning template; no application consumes it yet.
4. Identify the correct SDK versions for that host before installing dependencies. In particular, the spare original Nano and JetMax may have older operating systems and Python versions.
5. Develop arm status access and camera viewing before adding motion controls.

## Layout

- `config/`: examples with no real addresses or credentials.
- `docs/`: setup, decisions, verification records, and handoff notes.
- `scripts/`: reviewed utilities; currently local host inventory only.
- `local/`: ignored machine configuration, lab inventory, and diagnostic output.
- `data/`: ignored captures and calibration data; validated, non-sensitive calibration may be added deliberately later.

## Git workflow

Use this repository for all Lite 6/OAK work. Keep JetMax changes in its own repository. Review `git diff` and staged files, commit a coherent change, and push after each completed milestone. Never commit passwords, SSH private keys, access tokens, camera recordings, or unreviewed device logs. Record validation honestly: offline checks do not establish physical operation.

See [project status](docs/STATUS.md) for the next session.

## Camera discovery (development laptop)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-discovery.txt
.venv/bin/python scripts/discover_camera.py
```

This enumerates devices without opening a camera or starting a stream. No discovery result does not establish absence: power, subnet, cabling, firewall, and device state can affect discovery. These dependency versions were tested on the laptop, not on either Nano.

## Local live color preview

```bash
.venv/bin/python -m pip install -r requirements-preview.txt
.venv/bin/python scripts/camera_preview.py --ip <confirmed-camera-address>
```

Open `http://127.0.0.1:8090/` on this laptop. The preview requests CAM_A color at 640 x 400 and 15 FPS, with a small nonblocking queue. `/health` reports frame freshness; `/snapshot.jpg` returns a current JPEG; `/stream.mjpg` provides MJPEG. The server binds only to localhost, so other lab computers cannot access it directly. It does not continuously record images. Stop the foreground command with Ctrl+C. Do not launch a second instance while one is running.

This starts a temporary camera pipeline. It does not flash firmware, persist camera network settings, operate the IR emitters, or control the arm. The SDK may report optional bootloader updates; this utility does not perform them. Capture failure stops the process instead of automatically rebooting/reconnecting the device.

Verified on the laptop with OAK-D-PRO-POE and its OV9782 color sensor. The original Nano has not been validated. Based on the [official DepthAI camera output example](https://docs.luxonis.com/software-v3/depthai/examples/camera/camera_output).
