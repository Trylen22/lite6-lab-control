#!/usr/bin/env python3
"""Set up a Mac's lab Ethernet once, so the arm and camera are reachable after
every reboot, sleep and cable replug with no further commands.

Why this exists: the per-session fix (ifconfig aliases + a camera host route)
is forgotten by macOS on reboot or replug, and macOS otherwise sends all
169.254.x.x camera traffic out Wi-Fi. This installs one small LaunchDaemon
that, at boot and every 15 s, makes sure the wired adapter has

  * a 192.168.1.x address for the arm (default 192.168.1.201),
  * a 169.254.x.x address for the camera (macOS self-assigns one; if not,
    169.254.1.11),
  * host routes to the arm and the camera through that adapter.

It does nothing while the adapter is unplugged and never touches Wi-Fi, the
default route, the camera or the arm. Undo removes both installed files.

  .venv/bin/python scripts/mac_lab_network.py            # show the plan, ask, install
  .venv/bin/python scripts/mac_lab_network.py --yes      # install without asking
  .venv/bin/python scripts/mac_lab_network.py --undo
  options: --device enX   --arm-ip 192.168.1.201

Needs an administrator password (sudo) once. macOS Local Network permission
for the app that launches Python still has to be allowed by hand.
"""

import argparse
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_camera import mac_wired_adapters, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABEL = "local.lite6.lab-network"
PLIST = Path(f"/Library/LaunchDaemons/{LABEL}.plist")
HELPER = Path("/Library/Application Support/LITE6/lab-network.sh")
CAMERA_ALIAS = "169.254.1.11"


def station_addresses():
    """Arm and camera addresses, from the same config the deck uses."""
    for path in (ROOT / "local/lab.toml", ROOT / "config/lab.station.example.toml"):
        if path.exists():
            config = tomllib.loads(path.read_text())
            return config["robot"]["ip"], config["camera"]["ip"]
    return "192.168.1.152", "169.254.1.222"


def helper_script(dev, arm_ip, my_arm_ip, camera_ip):
    subnet = arm_ip.rsplit(".", 1)[0]
    return f"""#!/bin/sh
# Installed by LITE6 scripts/mac_lab_network.py (undo: --undo).
# Keeps the lab link on {dev} usable; does nothing while it is unplugged.
DEV={dev}
ifconfig "$DEV" 2>/dev/null | grep -q "status: active" || exit 0
ifconfig "$DEV" | grep -q "inet {my_arm_ip} " ||
  ifconfig "$DEV" inet {my_arm_ip} netmask 255.255.255.0 alias
ifconfig "$DEV" | grep -q "inet 169\\.254\\." ||
  ifconfig "$DEV" inet {CAMERA_ALIAS} netmask 255.255.0.0 alias
# Host routes win over Wi-Fi's link-local route and a home {subnet}.x network.
for HOST in {camera_ip} {arm_ip}; do
  route -n get "$HOST" 2>/dev/null | grep -q "interface: $DEV$" ||
    route -n change -host "$HOST" -interface "$DEV" >/dev/null 2>&1 ||
    route -n add -host "$HOST" -interface "$DEV" >/dev/null 2>&1
done
exit 0
"""


def plist_text():
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>{HELPER}</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>15</integer>
</dict>
</plist>
"""


def install_commands(helper_tmp, plist_tmp):
    return [
        ["sudo", "install", "-d", "-m", "755", str(HELPER.parent)],
        ["sudo", "install", "-m", "755", str(helper_tmp), str(HELPER)],
        ["sudo", "install", "-m", "644", str(plist_tmp), str(PLIST)],
        ["sudo", "launchctl", "bootout", f"system/{LABEL}"],  # may not be loaded
        ["sudo", "launchctl", "bootstrap", "system", str(PLIST)],
    ]


def undo_commands():
    return [
        ["sudo", "launchctl", "bootout", f"system/{LABEL}"],
        ["sudo", "rm", "-f", str(PLIST), str(HELPER)],
        ["sudo", "rmdir", str(HELPER.parent)],
    ]


def route_interface(host):
    code, text = run(["route", "-n", "get", host])
    for line in text.splitlines():
        if line.strip().startswith("interface:"):
            return line.split(":", 1)[1].strip()
    return None


def address_in_use(ip):
    code, _ = run(["ping", "-c", "1", "-t", "1", ip], timeout=5)
    return code == 0


def pick_device(requested):
    wired = mac_wired_adapters()
    if requested:
        return requested, next((w for w in wired if w[1] == requested), None)
    if not wired:
        sys.exit(
            "No active wired adapter. Plug the lab Ethernet in (link light on), "
            "or name it with --device enX (see: networksetup -listallhardwareports)."
        )
    if len(wired) > 1:
        names = ", ".join(f"{d} ({p})" for p, d, _ in wired)
        print(f"Several wired adapters are active: {names}. Using {wired[0][1]}; "
              "pass --device to choose another.")
    return wired[0][1], wired[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="wired adapter, e.g. en7 (default: the active one)")
    ap.add_argument("--arm-ip", default="192.168.1.201",
                    help="this Mac's address for the arm subnet (the Linux station uses .200)")
    ap.add_argument("--yes", action="store_true", help="install without asking")
    ap.add_argument("--undo", action="store_true", help="remove what this installed")
    a = ap.parse_args()
    if platform.system() != "Darwin":
        sys.exit("This is for macOS. Linux uses a NetworkManager profile: docs/LAB_SETUP.md.")

    if a.undo:
        for cmd in undo_commands():
            subprocess.run(cmd)
        print("Removed. Addresses added this session disappear at the next replug or reboot.")
        return 0

    arm_ip, camera_ip = station_addresses()
    dev, info = pick_device(a.device)
    addrs = info[2] if info else []
    if a.arm_ip not in addrs and address_in_use(a.arm_ip):
        sys.exit(f"{a.arm_ip} already answers on the network; pick a free one with --arm-ip.")

    print(f"Lab adapter: {dev}{f' ({info[0]})' if info else ''}, addresses now: "
          f"{', '.join(addrs) or 'none'}")
    print(f"Will install a LaunchDaemon that keeps, on {dev} only:")
    print(f"  {a.arm_ip}/24 for the arm at {arm_ip}")
    print(f"  a 169.254 address for the camera at {camera_ip}")
    print(f"  host routes to {camera_ip} and {arm_ip} through {dev}")
    print(f"Files: {PLIST}\n       {HELPER}")
    if not a.yes and input("Install? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        helper_tmp, plist_tmp = Path(tmp, "lab-network.sh"), Path(tmp, "lab.plist")
        helper_tmp.write_text(helper_script(dev, arm_ip, a.arm_ip, camera_ip))
        plist_tmp.write_text(plist_text())
        for cmd in install_commands(helper_tmp, plist_tmp):
            done = subprocess.run(cmd, capture_output="bootout" in cmd[2])
            if done.returncode != 0 and "bootout" not in cmd[2]:
                sys.exit(f"Failed: {' '.join(cmd)}")

    for _ in range(20):  # The daemon runs at load; give it a moment.
        if route_interface(camera_ip) == dev and route_interface(arm_ip) == dev:
            break
        time.sleep(0.5)
    ok = True
    for name, host in (("camera", camera_ip), ("arm", arm_ip)):
        iface = route_interface(host)
        print(f"{name:6} {host}: route via {iface}  {'OK' if iface == dev else 'NOT YET'}")
        ok &= iface == dev
    print("Installed: survives reboot, sleep and replug." if ok else
          "Installed, but routes are not on the lab adapter yet; is the cable in?")
    print("Next: .venv/bin/python scripts/diagnose_camera.py, then ./run.sh")
    print("If it says LOCAL NETWORK, allow your terminal app under System Settings › "
          "Privacy & Security › Local Network.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
