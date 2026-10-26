# macOS camera setup

The project has been tested on Linux x86_64 with Python 3.12. This Mac procedure combines the known station configuration with vendor troubleshooting guidance; it has not yet been validated on a collaborator's Mac. A connection failure needs its exact error before it can be attributed to networking, permissions, packages, or the camera.

## Check the Python environment first

Use Python 3.12 in a new virtual environment. The pinned NumPy requires Python 3.12 or newer; the Mac's default Python may not meet that requirement. Use a Python installation matching the Mac's architecture rather than mixing an Intel environment with Apple Silicon packages.

```bash
sw_vers
uname -m
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-deck.txt
.venv/bin/python -m pip check
.venv/bin/python -c 'import platform, depthai, cv2, numpy; print(platform.machine()); print("DepthAI", depthai.__version__); print("OpenCV", cv2.__version__); print("NumPy", numpy.__version__)'
```

If `python3.12` is unavailable, install Python 3.12 through your normal approved package source before creating the environment. If installation or imports fail, resolve that error before investigating camera discovery.

Published wheel metadata checked on 2026-10-26:

| Pinned package | macOS wheel availability |
|---|---|
| `depthai==3.11.0` | macOS 11+, both Apple Silicon and Intel |
| `numpy==2.5.4` | Python 3.12+; macOS wheels for both architectures |
| `opencv-contrib-python==5.0.0.93` | macOS 13+ Apple Silicon; macOS 14+ Intel |

These are package-distribution constraints, not proof that this application has passed a Mac hardware test. Older macOS versions may need a separately tested dependency set; do not silently change the shared requirements to work around one laptop's install failure.

Package references: [DepthAI](https://pypi.org/project/depthai/3.11.0/#files), [NumPy](https://pypi.org/project/numpy/2.5.4/#files), and [OpenCV](https://pypi.org/project/opencv-contrib-python/5.0.0.93/#files).

## Identify the lab Ethernet interface

Connect the Mac's Ethernet adapter to the lab switch. The OAK must receive PoE power. Do not assume the adapter is `en0`; that may identify Wi-Fi on a particular Mac.

```bash
networksetup -listallhardwareports
ifconfig
route -n get 169.254.1.222
route -n get 192.168.1.152
```

Match the Ethernet adapter's hardware port to its device name. The camera and arm require different subnets on that wired interface. Our Linux NetworkManager instructions do not apply to macOS.

## Add temporary lab addresses

Coordinate unused addresses with the station owner. The examples below use `enX` as a placeholder: replace it with the actual Ethernet device. `192.168.1.201` and `169.254.1.11` are candidates, not reserved assignments. Do not use these examples if another lab device already owns them. The original development laptop uses `.200` and `.10` respectively.

First inspect `ifconfig enX`. If the interface already has suitable host addresses, keep them rather than adding duplicates. Otherwise, temporary IPv4 aliases allow both devices to remain reachable without changing the camera's address:

```bash
sudo ifconfig enX inet 192.168.1.201 netmask 255.255.255.0 alias
sudo ifconfig enX inet 169.254.1.11 netmask 255.255.0.0 alias
```

Check the selected camera route again. If it points to Wi-Fi, a VPN, or another interface, add a specific route through the lab adapter:

```bash
sudo route -n add -host 169.254.1.222 -interface enX
route -n get 169.254.1.222
route -n get 192.168.1.152
ping -c 2 169.254.1.222
ping -c 2 192.168.1.152
```

If the route command reports that a route already exists, inspect it instead of repeatedly adding or deleting routes. A working robot ping does not establish a working camera route. Keep normal Wi-Fi Internet routing separate from this dedicated lab link. A VPN can also alter local routing.

These commands are temporary host-side configuration; they do not reconfigure either device. Remove only the aliases and explicit route you added when finished:

```bash
# Run the route removal only if you added that explicit host route above.
sudo route -n delete -host 169.254.1.222
sudo ifconfig enX inet 169.254.1.11 -alias
sudo ifconfig enX inet 192.168.1.201 -alias
```

For a recurring setup, have the Mac's owner choose a persistent network configuration rather than treating temporary aliases as a managed lab profile.

## Check local-network permission

On macOS versions that expose this control, open **System Settings > Privacy & Security > Local Network**. Allow the application actually launching Python when it appears, such as Terminal, iTerm, or the editor. A successful ping from one application does not prove that another application has permission to contact the camera. Review applicable firewall rules without disabling the system firewall globally.

Reference: [Apple: Control access to your local network](https://support.apple.com/guide/mac-help/control-access-to-your-local-network-on-mac-mchla4f49138/mac).

## Test the camera independently of the robot

Ensure the Linux laptop, OAK Viewer, and any other producer have released the camera. Coordinate a shutdown of an idle producer with its owner; do not interrupt a physical robot demonstration that depends on the stream.

From the repository root:

```bash
.venv/bin/python scripts/discover_camera.py
.venv/bin/python scripts/camera_preview.py --ip 169.254.1.222
```

Open `http://127.0.0.1:8090/` on this same Mac. The script specifies the camera IP directly, so success does not depend solely on broadcast discovery. `No devices discovered` is a discovery result, not proof that the explicit-IP connection cannot work.

The camera producer prints its device information and `First color frame received` after the first successful image. It has no robot control calls. If connection attempts time out despite correct routing and a free device, Luxonis documents longer boot timeouts as a diagnostic option:

```bash
DEPTHAI_WATCHDOG_INITIAL_DELAY=60000 DEPTHAI_BOOTUP_TIMEOUT=60000 .venv/bin/python scripts/camera_preview.py --ip 169.254.1.222
```

This cannot fix a wrong route, missing power, or denied network permission. Stop with Ctrl+C before trying another producer.

## Record the failure stage

| Result | Next evidence to collect |
|---|---|
| Package installation or import fails | macOS version, CPU architecture, Python version, and complete package error |
| Camera ping fails | Ethernet link/power, interface addresses, selected route, and network permission |
| Ping works, discovery finds nothing | Explicit-IP preview result and routing; broadcast discovery can behave differently |
| Device connection times out | Exact traceback, competing camera producers, permissions, VPN/firewall rules, and boot timeout |
| Device opens but no frames arrive | Device log, pipeline error, and the last printed startup message |
| Preview works but the deck does not | Deck log, local configuration, and producer freshness at `http://127.0.0.1:8090/health` |

Once the preview works, follow [Lab setup](LAB_SETUP.md) to create `local/lab.toml` and start the deck. Keep physical controls separate from this camera connection test.

Vendor reference: [Luxonis OAK PoE deployment and troubleshooting](https://docs.luxonis.com/hardware/platform/deploy/poe-deployment-guide), including its macOS routing, multiple-interface, firewall, and timeout guidance.
