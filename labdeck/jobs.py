"""Single-flight UI dispatch. This module contains NO hardware API calls.

Only an explicit POST starts a worker. Telemetry snapshots and page loads never
start jobs. Threads keep the video/status server responsive; the SDK's separate
motion lease also prevents competing controller processes.
"""

from datetime import datetime, timezone
import threading
import uuid

import numpy as np

from .automatic_pick import (
    PROFILE,
    check_observation_pose,
    check_transit,
    load_profile,
    run_cycle,
)


class JobManager:
    def __init__(self, runner=run_cycle, profile_path=PROFILE):
        self.runner = runner
        self.profile_path = profile_path
        self.lock = threading.Lock()
        self.worker = None
        self.data = {
            "state": "idle",
            "phase": "idle",
            "message": "Ready for checks",
            "job_id": None,
        }

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    def readiness(self, vision, robot):
        try:
            profile = load_profile(self.profile_path)
            if (
                not robot.get("fresh")
                or robot["values"].get("state") != 2
                or robot["values"].get("errors") != [0, 0]
            ):
                return False, "Robot must be connected, idle and error-free"
            check_observation_pose(robot["values"]["pose"], profile)
            if not vision.get("fresh"):
                return False, "Waiting for a fresh camera image"
            if (
                vision["settings"]["mode"] != "color"
                or vision["settings"]["preset"] != "green"
            ):
                return False, "Select green color detection"
            if len(vision["detections"]) != 1:
                return False, "Exactly one green marker must be visible"
            # Cached geometry only improves the button hint. The controller
            # independently acquires stable frames and rechecks live IK.
            start = robot["values"]["pose"]
            estimate = start.copy()
            center = np.array(vision["detections"][0]["center"], dtype=float)
            if center.shape != (2,) or not np.isfinite(center).all():
                return False, "Invalid target centroid"
            estimate[:2] = (
                np.array(start[:2])
                + np.linalg.solve(
                    profile["jacobian_px_per_mm"],
                    np.array(profile["cup_aim_px"]) - center,
                )
            ).tolist()
            check_transit(start, estimate, profile)
            return True, "One cycle · place back and return to camera height"
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            return False, str(exc)

    def start(self, vision, robot):
        with self.lock:
            if self.data["state"] == "running":
                raise RuntimeError("A pickup cycle is already running")
            ready, reason = self.readiness(vision, robot)
            if not ready:
                raise ValueError(reason)
            self.data = {
                "state": "running",
                "phase": "checking",
                "message": "Checking robot, tool and calibration",
                "job_id": uuid.uuid4().hex,
                "started_utc": datetime.now(timezone.utc).isoformat(),
            }
            self.worker = threading.Thread(
                target=self._run, args=(vision["settings"]["min_area"],), daemon=False
            )
            self.worker.start()
            return self.data.copy()

    def _run(self, min_area):
        def progress(phase, message):
            with self.lock:
                self.data.update(phase=phase, message=message)

        try:
            self.runner(
                profile_path=self.profile_path,
                progress=progress,
                min_area=min_area,
                execute=True,
            )
            with self.lock:
                self.data.update(
                    state="complete",
                    phase="complete",
                    message="Pick & Place complete · back at camera height",
                )
        except BaseException as exc:
            with self.lock:
                self.data.update(state="failed", phase="failed", message=str(exc))
        finally:
            with self.lock:
                self.data["finished_utc"] = datetime.now(timezone.utc).isoformat()

    def wait_for_completion(self):
        # Graceful server shutdown waits for an owned active cycle. Killing a
        # process/browser is NOT a robot stop. Use the physical E-stop to stop now.
        worker = self.worker
        if worker is not None:
            worker.join()
