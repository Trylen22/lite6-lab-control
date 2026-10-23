"""HTTP tests verify intent and dispatch exclusion without starting robot code."""

import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import Mock

from labdeck.server import make_handler
from test_pickup_jobs import Snapshot


class FollowHTTPTests(unittest.TestCase):
    def test_explicit_action_only_and_pickup_exclusion(self):
        vision = Snapshot({"settings": {"mode": "hands"}})
        robot = Snapshot({})
        follower = Mock()
        follower.snapshot.return_value = {"state": "idle"}
        follower.readiness.return_value = (True, "Ready")
        follower.start.return_value = {"state": "running", "token": "test-token"}
        follower.stop.return_value = {"state": "stopped"}
        follower.heartbeat.return_value = {"state": "running"}
        jobs = Mock()
        jobs.snapshot.return_value = {"state": "idle"}
        jobs.readiness.return_value = (False, "Select green")
        jobs.start.return_value = {"state": "running"}
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(vision, robot, threading.Event(), jobs, follower),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address)

        def post(path, body={}, action="hand-follow", origin=None):
            headers = {"Content-Type": "application/json"}
            if action:
                headers["X-Labdeck-Action"] = action
            if origin:
                headers["Origin"] = origin
            connection.request("POST", path, json.dumps(body), headers)
            response = connection.getresponse()
            data = json.loads(response.read())
            return response.status, data

        try:
            connection.request("GET", "/api/status")
            response = connection.getresponse()
            response.read()
            follower.start.assert_not_called()
            self.assertEqual(post("/api/follow/start", action=None)[0], 403)
            self.assertEqual(
                post("/api/follow/start", origin="http://elsewhere")[0], 403
            )
            self.assertEqual(post("/api/follow/start", {"x": 5})[0], 400)
            self.assertEqual(post("/api/follow/start")[0], 200)
            follower.start.assert_called_once()
            self.assertEqual(
                post("/api/follow/heartbeat", {"token": "test-token"})[0], 200
            )
            follower.heartbeat.assert_called_once_with("test-token")
            jobs.snapshot.return_value = {"state": "running"}
            self.assertEqual(post("/api/follow/start")[0], 400)
            self.assertEqual(post("/api/follow/stop")[0], 200)
            follower.stop.assert_called_once()
            jobs.snapshot.return_value = {"state": "idle"}
            follower.snapshot.return_value = {"state": "running"}
            self.assertEqual(post("/api/pick-place", action="pick-place")[0], 409)
            jobs.start.assert_not_called()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()
