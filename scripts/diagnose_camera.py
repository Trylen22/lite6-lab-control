#!/usr/bin/env python3
"""Find out WHY this computer can't reach the OAK camera, in one run.

Read-only: it asks the operating system how it would route to the camera,
pings it, tries one TCP connection to the camera's XLink port, and lists what
DepthAI discovery sees. It never opens the camera, starts a pipeline, or
changes any network setting. Run it once and act on the verdict; retrying a
connection in a loop cannot tell these causes apart.

Each failure looks the same from inside a connect/retry loop ("no device
found"), but they leave different evidence:
  * traffic leaves through the wrong interface (common on a Mac with Wi-Fi
    plus an Ethernet adapter: link-local 169.254.x.x goes out Wi-Fi)
  * no IP path at all (cable, PoE power, switch, or the camera has another
    address: 169.254.1.222 is only its fallback when no DHCP server answers)
  * macOS Local Network privacy: ping works (it is exempt) but Python's
    connection is refused with "No route to host" / "Operation not permitted"
  * a firewall dropping DepthAI's UDP discovery replies
  * another computer already has the camera open (it serves one host)

Usage:  python scripts/diagnose_camera.py [--ip 169.254.1.222]
"""

import argparse
import errno
import ipaddress
import os
import platform
import re
import socket
import subprocess
import sys

XLINK_TCP_PORT = 11490  # DepthAI XLink over TCP/IP
DISCOVERY_UDP_PORT = 11491  # DepthAI device discovery

SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"


def run(cmd, timeout=8):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)


def heading(text):
    print(f"\n== {text}")


def source_address(ip):
    """The local address the OS would send from (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, DISCOVERY_UDP_PORT))
        return s.getsockname()[0]
    except OSError as exc:
        return f"error: {exc}"
    finally:
        s.close()


def route_interface(ip):
    """(interface name, raw text) for the route the OS picks to ip."""
    if SYSTEM == "Darwin":
        code, text = run(["route", "-n", "get", ip])
        m = re.search(r"interface:\s*(\S+)", text)
        return (m.group(1) if m else None), text.strip()
    if SYSTEM == "Linux":
        code, text = run(["ip", "route", "get", ip])
        m = re.search(r"\bdev\s+(\S+)", text)
        return (m.group(1) if m else None), text.strip()
    if SYSTEM == "Windows":
        code, text = run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Find-NetRoute -RemoteIPAddress {ip} | Select-Object -First 1).InterfaceAlias",
            ]
        )
        name = text.strip().splitlines()[0] if text.strip() else None
        return name, text.strip()
    return None, "unsupported OS"


def interface_kind(name):
    """Best-effort label for an interface (Wi-Fi vs Ethernet)."""
    if not name:
        return "unknown"
    if SYSTEM == "Darwin":
        code, text = run(["networksetup", "-listallhardwareports"])
        block = re.search(
            r"Hardware Port: ([^\n]+)\nDevice: " + re.escape(name) + r"\b", text
        )
        return block.group(1).strip() if block else "unknown"
    if SYSTEM == "Linux":
        return (
            "Wi-Fi"
            if os.path.isdir(f"/sys/class/net/{name}/wireless")
            else "wired/other"
        )
    return "unknown"


def mac_wired_adapters():
    """Active non-Wi-Fi adapters on a Mac: [(hardware port, device, [IPv4s])]."""
    code, text = run(["networksetup", "-listallhardwareports"])
    found = []
    for port, dev in re.findall(r"Hardware Port: ([^\n]+)\nDevice: (\S+)", text):
        if re.search(r"Wi-?Fi|AirPort|Bluetooth|Thunderbolt Bridge", port, re.I):
            continue
        code, info = run(["ifconfig", dev])
        if "status: active" in info:
            found.append(
                (port.strip(), dev, re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", info))
            )
    return found


def mac_route_fix(ip, wrong_iface):
    """Concrete commands for the macOS link-local route problem."""
    wired = mac_wired_adapters()
    if not wired:
        return (
            "No active wired adapter found: check the Ethernet adapter is plugged in and its link light is on "
            "(System Settings › Network should show it as Connected or Self-Assigned IP)."
        )
    port, dev, addrs = wired[0]
    lines = [
        f"macOS sends ALL 169.254.x.x traffic out one interface; here that is {wrong_iface or '?'}, not your "
        f"wired adapter {dev} ({port}, addresses {', '.join(addrs) or 'none'}). Pick one fix:",
        "  1) quick test: turn Wi-Fi off, run this check again",
        f"  2) this session:  sudo route -n add -host {ip} -interface {dev}",
        f"     (if it says 'File exists':  sudo route -n change -host {ip} -interface {dev})",
        f"  3) lasting: System Settings › Network › ⋯ › Set Service Order…, drag {port} above Wi-Fi",
        "  4) permanent, recommended (survives reboot and replug):",
        "     .venv/bin/python scripts/mac_lab_network.py",
    ]
    if not any(a.startswith("169.254.") for a in addrs):
        lines.append(
            f"  {dev} also needs a link-local address:  sudo ifconfig {dev} inet 169.254.1.11 netmask 255.255.0.0 alias"
        )
    return "\n".join(lines)


def ping(ip):
    if SYSTEM == "Windows":
        cmd = ["ping", "-n", "2", "-w", "1000", ip]
    elif SYSTEM == "Darwin":
        cmd = ["ping", "-c", "2", "-t", "3", ip]
    else:
        cmd = ["ping", "-c", "2", "-W", "1", ip]
    code, text = run(cmd, timeout=10)
    return code == 0, text.strip().splitlines()[-1] if text.strip() else text


def tcp_probe(ip):
    """One TCP connection attempt to the XLink port, from THIS Python process."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((ip, XLINK_TCP_PORT))
        return "connected", None
    except socket.timeout:
        return "timeout", None
    except OSError as exc:
        return errno.errorcode.get(exc.errno, str(exc.errno)), exc
    finally:
        s.close()


def parent_apps():
    """On a Mac, the .app that launched this Python (Local Network permission
    is granted per app: Terminal, iTerm, VS Code, Cursor, …)."""
    apps, pid = [], os.getppid()
    for _ in range(12):
        code, text = run(["ps", "-o", "ppid=,comm=", "-p", str(pid)])
        if code != 0 or not text.strip():
            break
        ppid, _, comm = text.strip().partition(" ")
        m = re.search(r"/([^/]+)\.app/", comm)
        if m and m.group(1) not in apps:
            apps.append(m.group(1))
        if not ppid.strip().isdigit() or int(ppid) <= 1:
            break
        pid = int(ppid)
    return apps


def depthai_devices():
    try:
        import depthai as dai
    except Exception as exc:  # noqa: BLE001 - report any import failure
        return None, f"DepthAI import failed: {exc}"
    try:
        found = dai.Device.getAllConnectedDevices()
    except Exception as exc:  # noqa: BLE001
        return None, f"DepthAI discovery failed: {exc}"
    return [
        (d.name, str(d.state).split(".")[-1], str(d.protocol).split(".")[-1])
        for d in found
    ], dai.__version__


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--ip",
        default="169.254.1.222",
        help="camera address (default: the station's OAK)",
    )
    a = ap.parse_args()
    ip = a.ip
    link_local = ipaddress.ip_address(ip) in ipaddress.ip_network("169.254.0.0/16")
    findings = []

    heading("This computer")
    mac_version = (
        run(["sw_vers", "-productVersion"])[1].strip() if SYSTEM == "Darwin" else ""
    )
    print(
        f"{SYSTEM} {mac_version or platform.release()} · {platform.machine()} · Python {platform.python_version()}"
    )

    heading(f"Route to the camera ({ip})")
    iface, raw = route_interface(ip)
    kind = interface_kind(iface)
    src = source_address(ip)
    print(f"interface: {iface or '?'} ({kind}) · source address: {src}")
    if SYSTEM == "Darwin" and link_local:
        table = run(["netstat", "-rn", "-f", "inet"])[1]
        ll = [line for line in table.splitlines() if line.startswith("169.254")]
        print("169.254 routes:", *(ll or ["none"]), sep="\n  ")
    route_wrong = (
        (link_local and not str(src).startswith("169.254."))
        or "wi-fi" in kind.lower()
        or "airport" in kind.lower()
    )
    if route_wrong and SYSTEM == "Darwin":
        findings.append(("ROUTE", mac_route_fix(ip, iface)))
    elif link_local and not str(src).startswith("169.254."):
        findings.append(
            (
                "ROUTE",
                f"Packets to {ip} would leave from {src} on {iface or '?'} ({kind}), which has no 169.254.x.x "
                "address. Give the lab Ethernet adapter a link-local address and a host route to the camera "
                "(docs/MACOS_SETUP.md, 'Add temporary lab addresses').",
            )
        )
    elif "wi-fi" in kind.lower() or "airport" in kind.lower():
        findings.append(
            (
                "ROUTE",
                f"The camera route goes out {iface} ({kind}), not the Ethernet adapter. Add a host route through the lab adapter.",
            )
        )

    heading("Ping (system tool)")
    pinged, line = ping(ip)
    print(("reachable · " if pinged else "no reply · ") + line)

    heading(f"TCP connection from Python to {ip}:{XLINK_TCP_PORT}")
    result, exc = tcp_probe(ip)
    print(result + (f" ({exc})" if exc else ""))

    heading("DepthAI discovery (UDP broadcast)")
    devices, info = depthai_devices()
    if devices is None:
        print(info)
        findings.append(
            (
                "INSTALL",
                info + ". Fix the Python environment first (README, requirements.txt).",
            )
        )
    else:
        print(f"DepthAI {info}: {len(devices)} device(s)")
        for name, state, proto in devices:
            print(f"  {name}  state={state}  via {proto}")
    target = [d for d in (devices or []) if d[0] == ip]
    others = [d for d in (devices or []) if d[0] != ip and d[2].endswith("TCP_IP")]

    # ---- verdict, most specific first
    blocked_errors = {"EHOSTUNREACH", "EPERM", "EACCES", "ENETUNREACH"}
    if target and target[0][1] in ("X_LINK_BOOTED", "X_LINK_GATE_BOOTED"):
        findings.append(
            (
                "IN USE",
                "The camera is already open on another computer (state BOOTED). It serves one host at a time: stop the other deck, camera_preview or OAK Viewer, then try again.",
            )
        )
    if not pinged and others:
        findings.append(
            (
                "ADDRESS",
                f"No reply at {ip}, but discovery found an OAK at {', '.join(d[0] for d in others)}. The camera probably took a DHCP address; use that address (--ip, local/lab.toml).",
            )
        )
    elif not pinged:
        findings.append(
            (
                "NO PATH",
                f"Nothing answers at {ip}: check the Ethernet link light, that the OAK has PoE power (a plain Ethernet adapter gives none), the switch, and the route above.",
            )
        )
    if SYSTEM == "Darwin" and pinged and result in blocked_errors | {"timeout"}:
        apps = parent_apps()
        who = (
            ", ".join(apps)
            if apps
            else "the app you launched this from (Terminal, iTerm, VS Code, Cursor…)"
        )
        findings.append(
            (
                "LOCAL NETWORK",
                f"ping reaches the camera but Python can't connect ({result}). That is macOS Local Network privacy: allow {who} in System Settings › Privacy & Security › Local Network, then quit and reopen that app.",
            )
        )
    if (
        pinged
        and result in ("connected", "ECONNREFUSED")
        and devices is not None
        and not target
    ):
        findings.append(
            (
                "FIREWALL",
                "The camera answers ping and TCP, but DepthAI discovery doesn't see it: UDP discovery replies are being blocked. Allow incoming connections for Python in the firewall (macOS: System Settings › Network › Firewall › Options).",
            )
        )

    heading("Verdict")
    if not findings:
        state = target[0][1] if target else "not listed"
        print(
            f"No blocker found (camera state: {state}). Next: python scripts/camera_preview.py --ip {ip}"
        )
        return 0
    for tag, text in findings:
        print(f"[{tag}] {text}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
