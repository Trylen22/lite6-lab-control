"""The Mac lab-network installer writes a daemon that fixes the right adapter.

No macOS needed: the generated helper is checked as text and with `sh -n`.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mac_lab_network as mln  # noqa: E402


class MacLabNetworkTests(unittest.TestCase):
    def helper(self):
        return mln.helper_script("en7", "192.168.1.152", "192.168.1.201", "169.254.1.222")

    def test_helper_is_valid_shell_and_targets_only_the_lab_adapter(self):
        text = self.helper()
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            f.write(text)
            f.flush()
            self.assertEqual(subprocess.run(["sh", "-n", f.name]).returncode, 0)
        self.assertIn("DEV=en7", text)
        self.assertIn("inet 192.168.1.201 netmask 255.255.255.0 alias", text)
        self.assertIn(f"inet {mln.CAMERA_ALIAS} netmask 255.255.0.0 alias", text)
        self.assertIn("for HOST in 169.254.1.222 192.168.1.152", text)
        self.assertIn('grep -q "status: active" || exit 0', text)  # unplugged: no-op
        self.assertNotIn("default", text)  # never touches the default route
        self.assertNotIn("en0", text)

    def test_daemon_runs_at_boot_and_rechecks(self):
        plist = mln.plist_text()
        self.assertIn("<key>RunAtLoad</key><true/>", plist)
        self.assertIn("<integer>15</integer>", plist)
        self.assertIn(str(mln.HELPER), plist)

    def test_undo_removes_exactly_what_install_adds(self):
        installed = {c[-1] for c in mln.install_commands(Path("h"), Path("p"))[1:3]}
        removed = set(mln.undo_commands()[1][3:])
        self.assertEqual(installed, removed)

    def test_station_addresses_come_from_config(self):
        self.assertEqual(mln.station_addresses()[1], "169.254.1.222")


if __name__ == "__main__":
    unittest.main()
