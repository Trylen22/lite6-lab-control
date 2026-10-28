"""Published station calibration fills a fresh clone but never overwrites local/."""

from pathlib import Path
import tempfile
import unittest

from labdeck.station import STATION, seed_local


class StationSeedTests(unittest.TestCase):
    def test_fresh_clone_gets_every_profile_and_existing_files_are_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "local"
            (local / "calibration").mkdir(parents=True)
            (local / "automation.json").write_text('{"mine": true}')
            copied = seed_local(STATION, local)
            self.assertNotIn("automation.json", copied)
            self.assertEqual((local / "automation.json").read_text(), '{"mine": true}')
            for name in ("hand-follow.json", "shelf-place.json", "start-poses.json",
                         "taught_poses/controller-tool-report.json"):
                self.assertTrue((local / name).exists(), name)
            self.assertEqual(seed_local(STATION, local), [])  # second launch: no-op


if __name__ == "__main__":
    unittest.main()
