# Lab setup and first access

This guide distinguishes the known shared station from a new installation. For coding-agent setup and a hardware-free Lab preview, start with [Agent setup](AGENT_SETUP.md).

For macOS, use [Mac camera setup](MACOS_SETUP.md) for interface discovery, temporary addresses, routing, local-network permission, and dependency constraints. The NetworkManager commands and profiles described below are Linux-specific.

## Known shared station

These values were read from the working station configuration and the laptop's saved `lite6-lab` NetworkManager profile on 2026-10-26. They are installation records, not a live connectivity check or factory defaults for every Lite6/OAK setup.

| Component | Address | Notes |
|---|---|---|
| UFACTORY Lite6 controller | `192.168.1.152` | Address passed to the UFACTORY SDK |
| Luxonis OAK-D Pro PoE | `169.254.1.222` | Camera address passed to DepthAI; link-local subnet |
| Original development laptop, robot side | `192.168.1.200/24` | Saved wired-profile address; do not assign it to a second laptop |
| Original development laptop, camera side | `169.254.1.10/16` | Second address on the same wired interface |
| Camera-subnet route | `169.254.0.0/16` | Explicit route through that wired interface in the saved profile |
| Suction tool | No separate IP | Controlled through the arm's tool I/O |
| Local Lab Deck | `http://127.0.0.1:8100/` | Runs on the host computer, not on the robot |
| Local camera preview | `http://127.0.0.1:8090/` | Created by `scripts/camera_preview.py` on the host |

The robot and camera are on different subnets even though they share an Ethernet switch. A successful robot connection does not establish camera reachability. The camera needs PoE power. The switch management address has not been confirmed; no switch login is required by this application. There is no established permanent SSH host for this project.

For a second laptop, select unused host addresses on both subnets with the station owner. For example, `192.168.1.201/24` and `169.254.1.11/16` are candidates only if confirmed unused. Keep the device addresses above unchanged. In a dedicated wired NetworkManager profile, add both host addresses and an explicit `169.254.0.0/16` route through the wired interface. This lab-only connection does not need a default gateway; preserve the computer's normal Internet connection separately. Turn autoconnect on (`nmcli connection modify lite6-lab connection.autoconnect yes connection.autoconnect-retries 0`) so the link returns by itself at boot, wake and cable replug; it was off on the original laptop until 2026-10-28.

Inspect the selected interface and routes before changing them:

```bash
ip -br -4 address
ip route get 192.168.1.152
ip route get 169.254.1.222
ping -c 2 192.168.1.152
ping -c 2 169.254.1.222
```

Both routes should use the lab's wired interface. The camera route should select its link-local host address. Ping only checks network reachability; DepthAI discovery and a fresh image establish separate stages of camera access.

## Configure this station's addresses

From a fresh clone, after creating `.venv` and installing `requirements-deck.txt` as shown in the README:

```bash
mkdir -p local
cp --no-clobber config/lab.station.example.toml local/lab.toml
```

Inspect `local/lab.toml`. The station example supplies the two known device IPs. If that file already exists, the command preserves it; compare its values rather than assuming the example replaced them. For a different installation, start from the blank `config/lab.example.toml` instead.

The validation fields are operator notes, not software motion gates. An address configuration is not calibration.

## Establish camera viewing and telemetry

Only one producer should own the OAK device at a time. Coordinate with anyone already running a stream before opening it.

```bash
# Enumerate devices; this does not start an image pipeline.
.venv/bin/python scripts/discover_camera.py

# Full launcher: start or reuse the camera producer, then start the deck.
./run.sh
```

The launcher reads `local/lab.toml`, reuses an existing fresh producer on port 8090, and stops only its own children on Ctrl+C. It does not require SSH into the camera or arm.

To run the processes separately:

```bash
# Terminal 1
.venv/bin/python scripts/camera_preview.py --ip 169.254.1.222

# Terminal 2, from the repository root
.venv/bin/python -m labdeck.server
```

Open the camera preview at `http://127.0.0.1:8090/` and the simulator at `http://127.0.0.1:8100/#lab`. These services bind to loopback, so another laptop's browser cannot reach them using its own `127.0.0.1`.

**Physical controls:** selecting Color detection or Hand puppy can move the arm to a taught demo pose. Start following, Pick & Place, and Pick to Shelf also issue physical commands. Use `/#lab` for a programming-only session. Confirm mounting, tool/load settings, emergency-stop access, clear space, and current local profiles before an operator requests a physical demonstration.

## What cloning does not transfer

Git excludes the station's `local/` directory: device runtime configuration, contact references, pickup fit, hand-follow anchor, start joints, shelf route, optional simulator fit, models, and trial logs. The known network example is published; the measured motion data remains local.

For this same unchanged station, arrange a supervised handoff of the applicable validated profiles from its owner. For another arm, camera mount, tool, or workspace, establish the relevant measurements instead of copying poses. The nominal simulator can run without a per-arm kinematic fit. See [Agent setup](AGENT_SETUP.md) for the file map and [Calibration plan](CALIBRATION_PLAN.md) for measurement work.

## New or changed installation

Record the equipment labels, base mounting, camera mount, tool, cables, power/PoE, host software, and existing network configuration in ignored `local/inventory.md`. Run `scripts/host_inventory.sh` for a read-only host inventory. Confirm device addresses with the lab operator; do not reuse JetMax addresses, scan unrelated networks, or reset device networking to guess an address.

Remote SSH access, if needed later, connects to a configured host running the software. The repository does not define a permanent lab desktop account or shared SSH credential.

## References and historical discovery

The OAK was originally discovered at `169.254.1.222` after the laptop received a second Ethernet address and an explicit link-local route. Earlier scans restricted to the arm's subnet missed it. That discovery explains the two-subnet setup above; it does not mean a browser stream runs on the camera itself.

- [UFACTORY Studio connection](https://docs.usermanual.ufactory.cc/user_manual/ufactoryStudio/3.connection.html)
- [UFACTORY Python SDK](https://github.com/xArm-Developer/xArm-Python-SDK)
- [OAK-D Pro PoE hardware](https://docs.luxonis.com/hardware/products/OAK-D%20Pro%20PoE)
- [Luxonis PoE deployment](https://docs.luxonis.com/hardware/platform/deploy/poe-deployment-guide)
- [Calibration plan](CALIBRATION_PLAN.md)
