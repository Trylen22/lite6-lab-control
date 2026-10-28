"""The camera diagnostic names the right cause for each failure pattern.

Probes are replaced with fakes, so these run on any OS without a camera.
"""

import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_camera as dc  # noqa: E402

IP = "169.254.1.222"


def verdict(
    system="Darwin",
    iface=("en7", "USB 10/100/1000 LAN"),
    src="169.254.1.11",
    pinged=True,
    tcp="connected",
    devices=((IP, "X_LINK_UNBOOTED", "X_LINK_TCP_IP"),),
    apps=("Terminal",),
):
    out = io.StringIO()
    with (
        patch.object(dc, "SYSTEM", system),
        patch.object(dc, "route_interface", return_value=(iface[0], "")),
        patch.object(dc, "interface_kind", return_value=iface[1]),
        patch.object(dc, "source_address", return_value=src),
        patch.object(dc, "ping", return_value=(pinged, "")),
        patch.object(dc, "tcp_probe", return_value=(tcp, None)),
        patch.object(dc, "depthai_devices", return_value=(list(devices), "3.11.0")),
        patch.object(dc, "parent_apps", return_value=list(apps)),
        patch.object(dc, "run", return_value=(0, "15.1")),
        patch.object(sys, "argv", ["diagnose_camera.py"]),
        contextlib.redirect_stdout(out),
    ):
        code = dc.main()
    text = out.getvalue().split("== Verdict", 1)[1]
    return code, text


class DiagnoseCameraTests(unittest.TestCase):
    def test_healthy_station(self):
        code, text = verdict()
        self.assertEqual(code, 0)
        self.assertIn("No blocker found", text)

    def test_mac_local_network_privacy(self):
        code, text = verdict(tcp="EHOSTUNREACH", apps=("Cursor",))
        self.assertEqual(code, 1)
        self.assertIn("[LOCAL NETWORK]", text)
        self.assertIn("Cursor", text)

    def test_link_local_leaves_through_wifi(self):
        code, text = verdict(
            iface=("en0", "Wi-Fi"),
            src="10.0.0.5",
            pinged=False,
            tcp="timeout",
            devices=(),
        )
        self.assertIn("[ROUTE]", text)
        self.assertIn("[NO PATH]", text)

    def test_camera_open_on_another_computer(self):
        code, text = verdict(devices=((IP, "X_LINK_BOOTED", "X_LINK_TCP_IP"),))
        self.assertIn("[IN USE]", text)

    def test_camera_took_a_dhcp_address(self):
        code, text = verdict(
            pinged=False,
            tcp="timeout",
            devices=(("192.168.1.77", "X_LINK_UNBOOTED", "X_LINK_TCP_IP"),),
        )
        self.assertIn("[ADDRESS]", text)
        self.assertIn("192.168.1.77", text)

    def test_firewall_blocks_discovery_replies(self):
        code, text = verdict(devices=())
        self.assertIn("[FIREWALL]", text)

    def test_mac_route_fix_names_the_wired_adapter(self):
        # Real-shaped macOS output: Wi-Fi is en0, a USB Ethernet adapter is en7
        # with a self-assigned 169.254 address, but the route goes out en0.
        ports = (
            "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa\n\n"
            "Hardware Port: USB 10/100/1000 LAN\nDevice: en7\nEthernet Address: bb\n\n"
            "Hardware Port: Thunderbolt Bridge\nDevice: bridge0\nEthernet Address: cc\n"
        )
        ifconfig = {
            "en7": "en7: flags=8863<UP>\n\tinet 169.254.32.7 netmask 0xffff0000\n\tstatus: active\n",
            "bridge0": "bridge0: flags=8863<UP>\n\tstatus: inactive\n",
        }

        def fake_run(cmd, timeout=8):
            if cmd[0] == "networksetup":
                return 0, ports
            if cmd[0] == "ifconfig":
                return 0, ifconfig.get(cmd[1], "")
            return 0, ""

        with patch.object(dc, "run", side_effect=fake_run):
            text = dc.mac_route_fix(IP, "en0")
        self.assertIn("not your wired adapter en7 (USB 10/100/1000 LAN", text)
        self.assertIn(f"sudo route -n add -host {IP} -interface en7", text)
        self.assertIn("route -n change", text)
        self.assertIn("Set Service Order", text)
        self.assertIn("scripts/mac_lab_network.py", text)
        self.assertNotIn("ifconfig en7 inet", text)  # it already has 169.254

    def test_local_network_verdict_is_mac_only(self):
        code, text = verdict(
            system="Linux", tcp="EHOSTUNREACH", iface=("enp8s0", "wired/other")
        )
        self.assertNotIn("[LOCAL NETWORK]", text)


if __name__ == "__main__":
    unittest.main()
