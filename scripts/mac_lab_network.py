#!/usr/bin/env python3
"""Set up a Mac's lab Ethernet once, so the arm and camera are reachable after
every reboot, sleep and cable replug with no further commands.

Why this exists: the per-session fix (ifconfig aliases + a camera host route)
is forgotten by macOS on reboot or replug, and macOS otherwise sends all
169.254.x.x camera traffic out Wi-Fi. This installs one small LaunchDaemon
that, at boot and every 15 s, makes sure the wired adapter has

  * a 192.168.1.x address for the arm (keeps one you set, else 192.168.1.201),
  * a 169.254.x.x address for the camera (macOS self-assigns one; if not,
    169.254.1.11),
  * the 169.254.0.0/16 route on that adapter, sending FROM its 169.254
    address. Tested failure on a Mac (2026-10-28): with the adapter set to
    192.168.1.100, camera packets left from .100 and the camera, which only
    knows link-local, never answered. A "-host ... -interface" route is worse:
    macOS maps the camera to the Mac's own MAC. Both are cleaned up here.

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
import re
import subprocess
import sys
import tempfile
import time
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_camera import mac_wired_adapters, run, source_address  # noqa: E402

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
    subnet = re.escape(arm_ip.rsplit(".", 1)[0] + ".")
    return f"""#!/bin/sh
# Installed by LITE6 scripts/mac_lab_network.py (undo: --undo).
# Keeps the lab link on {dev} usable; does nothing while it is unplugged.
DEV={dev}
STATE=/var/run/lite6-lab-network
ifconfig "$DEV" 2>/dev/null | grep -q "status: active" || {{ rm -f "$STATE"; exit 0; }}
# Arm subnet: keep any address the owner already set, else add ours.
ifconfig "$DEV" | grep -q "inet {subnet}" ||
  ifconfig "$DEV" inet {my_arm_ip} netmask 255.255.255.0 alias
ifconfig "$DEV" | grep -q "inet 169\\.254\\." ||
  ifconfig "$DEV" inet {CAMERA_ALIAS} netmask 255.255.0.0 alias
LL=$(ifconfig "$DEV" | awk '$1=="inet" && $2 ~ /^169\\.254\\./ {{print $2; exit}}')
[ -n "$LL" ] || exit 0
ROUTE=$(route -n get {camera_ip} 2>/dev/null)
# "route add -host CAMERA -interface DEV" maps the camera to this Mac's own
# MAC address, so nothing ever reaches it. Remove such a static host route.
if echo "$ROUTE" | grep "flags:" | grep HOST | grep -q STATIC; then
  route -n delete -host {camera_ip} >/dev/null 2>&1
  arp -d {camera_ip} >/dev/null 2>&1
  rm -f "$STATE"
fi
if echo "$ROUTE" | grep -q "interface: $DEV$" &&
  [ "$(cat "$STATE" 2>/dev/null)" = "$DEV $LL" ]; then
  exit 0
fi
# The whole link-local range out the lab adapter, SENT FROM its 169.254
# address (-ifa): the camera has no route back to any other source address.
{{ route -n change -net 169.254.0.0 -netmask 255.255.0.0 -interface "$DEV" -ifa "$LL" ||
  route -n add -net 169.254.0.0 -netmask 255.255.0.0 -interface "$DEV" -ifa "$LL"; }} \\
  >/dev/null 2>&1 && echo "$DEV $LL" > "$STATE"
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
    subnet = arm_ip.rsplit(".", 1)[0] + "."
    mine = next((x for x in addrs if x.startswith(subnet)), None)
    if mine:
        a.arm_ip = mine  # Keep the address the owner already set.
    elif address_in_use(a.arm_ip):
        sys.exit(f"{a.arm_ip} already answers on the network; pick a free one with --arm-ip.")
    other = route_interface(arm_ip)
    if other and other != dev and not mine:
        print(f"Note: {subnet}x currently routes via {other} (a home network on the same "
              f"subnet?). The arm needs {dev}; if it stays unreachable, leave that network.")

    print(f"Lab adapter: {dev}{f' ({info[0]})' if info else ''}, addresses now: "
          f"{', '.join(addrs) or 'none'}")
    print(f"Will install a LaunchDaemon that keeps, on {dev} only:")
    print(f"  {a.arm_ip}/24 for the arm at {arm_ip}" + (" (already set; kept)" if mine else ""))
    print(f"  a 169.254 address for the camera at {camera_ip}")
    print(f"  the 169.254.0.0/16 route on {dev}, sent from that 169.254 address")
    print("  and removes a broken '-host ... -interface' camera route if one exists")
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

    def camera_ok():
        return route_interface(camera_ip) == dev and str(
            source_address(camera_ip)).startswith("169.254.")

    for _ in range(20):  # The daemon runs at load; give it a moment.
        if camera_ok():
            break
        time.sleep(0.5)
    src = source_address(camera_ip)
    cam = route_interface(camera_ip)
    arm = route_interface(arm_ip)
    print(f"camera {camera_ip}: via {cam} from {src}  {'OK' if camera_ok() else 'NOT YET'}")
    print(f"arm    {arm_ip}: via {arm}  {'OK' if arm == dev else 'NOT YET'}")
    ok = camera_ok() and arm == dev
    print("Installed: survives reboot, sleep and replug." if ok else
          "Installed, but the lab adapter is not carrying both yet; is the cable in?")
    print("Next: .venv/bin/python scripts/diagnose_camera.py, then ./run.sh")
    print("If it says LOCAL NETWORK, allow your terminal app under System Settings › "
          "Privacy & Security › Local Network.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
