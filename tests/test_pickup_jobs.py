"""Dispatch/HTTP tests use fake observations and a fake runner, never hardware."""

from datetime import datetime, timedelta, timezone
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from labdeck.jobs import JobManager
from labdeck.server import make_handler


def profile_fixture():
    return {
        "schema": 1,
        "profile_id": "test-only",
        "expires_utc": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "speed_scale": 1.3225,
        "jacobian_px_per_mm": [[0, -2], [-2, 0]],
        "xy_min_mm": [100, 0],
        "xy_max_mm": [300, 150],
        "observation_height_mm": 266,
        "contact_floor_z_mm": 95,
        "orientation_degrees": [180, 0, 0],
        "cup_aim_px": [330, 60],
        "resolution": [640, 400],
        "camera_session": "fake-camera",
    }


class Snapshot:
    def __init__(self, data):
        self.data = data

    def snapshot(self):
        return self.data


class PickupJobsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.profile = Path(self.folder.name) / "profile.json"
        self.profile.write_text(json.dumps(profile_fixture()))
        self.vision = {
            "fresh": True,
            "settings": {"mode": "color", "preset": "green", "min_area": 100},
            "detections": [{"label": "green", "center": [330, 60]}],
        }
        self.robot = {
            "fresh": True,
            "values": {"state": 2, "errors": [0, 0], "pose": [200, 70, 266, 180, 0, 0]},
        }
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []

        def runner(**kwargs):
            self.calls.append(kwargs)
            kwargs["progress"]("aligning", "Fake alignment")
            self.entered.set()
            self.release.wait(3)

        self.jobs = JobManager(runner=runner, profile_path=self.profile)

    def tearDown(self):
        self.release.set()
        self.jobs.wait_for_completion()
        self.folder.cleanup()

    def test_no_job_on_initialization_or_status_and_duplicate_start_rejected(self):
        self.assertEqual(self.jobs.snapshot()["state"], "idle")
        self.assertEqual(self.calls, [])
        self.jobs.start(self.vision, self.robot)
        self.assertTrue(self.entered.wait(1))
        with self.assertRaises(RuntimeError):
            self.jobs.start(self.vision, self.robot)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0]["execute"])
        self.release.set()
        self.jobs.wait_for_completion()
        self.assertEqual(self.jobs.snapshot()["state"], "complete")

    def test_completed_job_displays_measured_duration(self):
        self.jobs.runner = lambda **kwargs: {
            "total_seconds": 45.2,
            "phase_seconds": {"approaching": 12},
        }
        self.jobs.start(self.vision, self.robot)
        self.jobs.wait_for_completion()
        result = self.jobs.snapshot()
        self.assertEqual(result["total_seconds"], 45.2)
        self.assertIn("45.2 s", result["message"])
        self.assertEqual(result["phase_seconds"], {"approaching": 12})

    def test_fault_is_reported_without_automatic_retry(self):
        def fail(**kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("No seal; released, no lift")

        self.jobs.runner = fail
        self.jobs.start(self.vision, self.robot)
        self.jobs.wait_for_completion()
        self.assertEqual(self.jobs.snapshot()["state"], "failed")
        self.assertIn("No seal", self.jobs.snapshot()["message"])
        self.assertEqual(len(self.calls), 1)

    def test_unready_height_ambiguous_target_and_expired_profile_block_dispatch(self):
        for problem in ["height", "camera", "multiple", "state"]:
            with self.subTest(problem=problem):
                vision = json.loads(json.dumps(self.vision))
                robot = json.loads(json.dumps(self.robot))
                self.profile.write_text(json.dumps(profile_fixture()))
                if problem == "height":
                    robot["values"]["pose"][2] = 330
                if problem == "camera":
                    vision["fresh"] = False
                if problem == "multiple":
                    vision["detections"] *= 2
                if problem == "state":
                    robot["values"]["state"] = 5
                with self.assertRaises(ValueError):
                    self.jobs.start(vision, robot)
        self.assertEqual(self.calls, [])

    def test_visible_but_out_of_region_target_disables_button(self):
        self.vision["detections"][0]["center"] = [0, 0]
        ready, reason = self.jobs.readiness(self.vision, self.robot)
        self.assertFalse(ready)
        self.assertIn("Outside", reason)
        self.assertEqual(self.calls, [])

    def test_http_only_explicit_local_action_starts_one_fake_job(self):
        stop = threading.Event()
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(Snapshot(self.vision), Snapshot(self.robot), stop, self.jobs),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port

        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = json.loads(response.read())
            conn.close()
            return response.status, data

        try:
            code, data = request("GET", "/api/status")
            self.assertEqual(code, 200)
            self.assertTrue(data["pickup"]["ready"])
            self.assertEqual(self.calls, [])
            headers = {
                "Content-Type": "application/json",
                "X-Labdeck-Action": "pick-place",
                "Origin": f"http://127.0.0.1:{port}",
            }
            self.assertEqual(
                request(
                    "POST",
                    "/api/pick-place",
                    "{}",
                    {**headers, "Origin": "https://untrusted.example"},
                )[0],
                403,
            )
            self.assertEqual(
                request(
                    "POST",
                    "/api/pick-place",
                    "{}",
                    {"Content-Type": "application/json"},
                )[0],
                403,
            )
            self.assertEqual(
                request("POST", "/api/pick-place", '{"x":999}', headers)[0], 400
            )
            self.assertEqual(self.calls, [])
            self.assertEqual(request("POST", "/api/pick-place", "{}", headers)[0], 202)
            self.assertTrue(self.entered.wait(1))
            self.assertEqual(request("POST", "/api/pick-place", "{}", headers)[0], 409)
            self.assertEqual(len(self.calls), 1)
        finally:
            self.release.set()
            self.jobs.wait_for_completion()
            server.shutdown()
            server.server_close()
            thread.join(2)
