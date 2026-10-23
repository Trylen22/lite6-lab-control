"""Measure small wrist turns for a head-following demo.

Default is read-only IK preview. Execution needs --execute --space-clear and an
already enabled/idle controller. Static scene feature flow supplies image-motion
DIRECTIONS; unknown scene/hand depth prevents a metric hand-distance claim.
A full return-to-origin check and independent holdout reject moving scenes.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import time
import urllib.request
import uuid

import cv2
import numpy as np

from .calibration_motion import ROOT
from .hand_motion import HandWristArm
from .green_calibrate import save


def frame(after=None):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with urllib.request.urlopen(
            "http://127.0.0.1:8090/observation.json", timeout=1
        ) as response:
            packet = json.load(response)
        if not packet["fresh"] or time.monotonic() - packet["received_monotonic"] > 0.5:
            raise RuntimeError("Calibration camera is stale")
        if after is None or packet["sequence"] > after:
            image = cv2.imdecode(
                np.frombuffer(base64.b64decode(packet["jpeg_base64"]), np.uint8),
                cv2.IMREAD_GRAYSCALE,
            )
            if image is None:
                raise RuntimeError("Invalid calibration frame")
            return image, packet
        time.sleep(0.03)
    raise RuntimeError("Camera did not provide a distinct frame")


class SceneFlow:
    def __init__(self, image, roi=None, exclude_roi=None):
        self.image = image
        mask = None
        if roi is not None:
            x, y, width, height = roi
            if (
                min(x, y) < 0
                or min(width, height) <= 0
                or x + width > image.shape[1]
                or y + height > image.shape[0]
            ):
                raise ValueError("Invalid stationary-scene ROI")
            mask = np.zeros_like(image)
            mask[y : y + height, x : x + width] = 255
        if exclude_roi is not None:
            if mask is None:
                mask = np.full_like(image, 255)
            x, y, width, height = exclude_roi
            if (
                min(x, y) < 0
                or min(width, height) <= 0
                or x + width > image.shape[1]
                or y + height > image.shape[0]
            ):
                raise ValueError("Invalid moving-subject exclusion")
            mask[y : y + height, x : x + width] = 0
        self.points = cv2.goodFeaturesToTrack(
            image, maxCorners=200, qualityLevel=0.005, minDistance=8, mask=mask
        )
        if self.points is None or len(self.points) < 30:
            raise RuntimeError("Not enough stationary scene texture for calibration")

    def measure(self, image):
        shifted, status, _ = cv2.calcOpticalFlowPyrLK(
            self.image, image, self.points, None
        )
        if shifted is None:
            raise RuntimeError("Scene flow failed")
        reverse, back_status, _ = cv2.calcOpticalFlowPyrLK(
            image, self.image, shifted, None
        )
        if reverse is None:
            raise RuntimeError("Scene flow reverse check failed")
        valid = (
            (status[:, 0] > 0)
            & (back_status[:, 0] > 0)
            & (np.linalg.norm(reverse[:, 0] - self.points[:, 0], axis=1) < 0.5)
        )
        flows = (shifted[:, 0] - self.points[:, 0])[valid]
        if len(flows) < 25:
            raise RuntimeError("Too few consistent scene features")
        # A wrist turn produces a projective image warp. Fit that spatial
        # field instead of pretending all ceiling features translate equally.
        source_points = self.points[:, 0][valid]
        destination_points = shifted[:, 0][valid]
        transform, support = cv2.findHomography(
            source_points, destination_points, cv2.RANSAC, 0.6
        )
        if (
            transform is None
            or support is None
            or support.sum() < 25
            or support.mean() < 0.65
        ):
            raise RuntimeError("Scene projective fit failed")
        center = np.float32([[[self.image.shape[1] / 2, self.image.shape[0] / 2]]])
        shifted_center = cv2.perspectiveTransform(center, transform)[0, 0]
        return (shifted_center - center[0, 0]).astype(float), int(support.sum())


def calibrate(execute=False, space_clear=False, roi=None, exclude_roi=None):
    if execute and not space_clear:
        raise ValueError("Operator must confirm clear probe space")
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "execute": execute,
        "samples": [],
        "stationary_scene_roi": roi,
        "moving_subject_exclusion": exclude_roi,
    }
    path = ROOT / "local/calibration/hand-response-probes.json"
    try:
        with HandWristArm() as robot:
            start = robot.check()
            image, packet = frame()
            record.update(start=start, camera_session=packet["session"])
            targets = []
            for axis in [3, 4]:
                for direction in [1, -1]:
                    target = start.copy()
                    target[axis] += direction
                    robot.preview(target)
                    targets.append((axis, direction, target))
            record["result"] = "read_only_probe_paths_passed"
            if not execute:
                return record
            flow = SceneFlow(image, roi=roi, exclude_roi=exclude_roi)
            responses = {axis: [] for axis in [3, 4]}

            def measurement():
                # Mechanical settling and the camera's queued frame can outlast
                # SDK completion. Acquire a bounded stable window, not the first
                # three frames indiscriminately. Do not relax residual limits.
                time.sleep(0.3)
                previous = frame()[1]["sequence"]
                observations = []
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    current, meta = frame(previous)
                    previous = meta["sequence"]
                    if meta["session"] != packet["session"]:
                        raise RuntimeError("Camera session changed")
                    try:
                        delta, inliers = flow.measure(current)
                    except RuntimeError:
                        observations = []
                        continue  # A bad video frame is not a usable measurement.
                    observations.append(delta)
                    observations = observations[-3:]
                    if (
                        len(observations) == 3
                        and max(
                            np.linalg.norm(delta - np.mean(observations, axis=0))
                            for delta in observations
                        )
                        <= 0.5
                    ):
                        return np.mean(observations, axis=0), inliers
                raise RuntimeError("Scene did not settle within three seconds")

            for axis, direction, target in targets:
                # Refresh the local image reference at the encoder-verified
                # anchor. Changes in exposure/person over the whole experiment
                # must not accumulate as a false camera-translation intercept.
                image, packet = frame()
                flow = SceneFlow(image, roi=roi, exclude_roi=exclude_roi)
                robot.move(target, speed=2)
                shift, inliers = measurement()
                responses[axis].append(shift / direction)
                record["samples"].append(
                    {
                        "axis": axis,
                        "offset_degrees": direction,
                        "shift_px": shift.tolist(),
                        "inliers": inliers,
                    }
                )
                save(path, record)
                robot.move(start, speed=2)
                returned, _ = measurement()
                record.setdefault("return_residuals_px", []).append(
                    float(np.linalg.norm(returned))
                )
                save(path, record)
                if np.linalg.norm(returned) > 2:
                    raise RuntimeError("Scene moved while returning to origin")
            response = np.array([np.mean(responses[a], axis=0) for a in [3, 4]]).T
            # Both probe directions must agree, not merely average into a fit.
            if any(
                np.linalg.norm(responses[a][0] - responses[a][1]) > 1.5 for a in [3, 4]
            ):
                raise RuntimeError("Opposing probe responses disagree")
            axes, j = [3, 4], response
            if np.linalg.cond(j) > 5 or min(np.linalg.svd(j, compute_uv=False)) < 0.5:
                raise RuntimeError("Wrist image response is ill-conditioned")
            holdout = start.copy()
            for axis in axes:
                holdout[axis] += 0.5
            robot.preview(holdout)
            robot.move(holdout, speed=2)
            measured, _ = measurement()
            residual = float(np.linalg.norm(measured - j @ np.array([0.5, 0.5])))
            record.update(
                plane_axes=axes,
                response_px_per_degree=response.tolist(),
                holdout_error_px=residual,
            )
            if residual > 2:
                raise RuntimeError("Independent hand response holdout failed")
            robot.move(start, speed=2)
            returned, _ = measurement()
            if np.linalg.norm(returned) > 2:
                raise RuntimeError("Scene changed after holdout")
            # The follow session is bounded to this newly inspected plane.
            # Preview corners/center without physically traversing the area.
            record["workspace_previews"] = []
            for first in [-5, 0, 5]:
                for second in [-5, 0, 5]:
                    edge = start.copy()
                    edge[axes[0]] += first
                    edge[axes[1]] += second
                    record["workspace_previews"].append(robot.preview(edge))
            now = datetime.now(timezone.utc)
            profile = {
                "hand_schema": 2,
                "profile_id": uuid.uuid4().hex,
                "camera_session": packet["session"],
                "resolution": [640, 400],
                "anchor_joints_deg": start,
                "joint_axes": axes,
                "joint_min_deg": (np.array(start)[axes] - 5).tolist(),
                "joint_max_deg": (np.array(start)[axes] + 5).tolist(),
                "jacobian_px_per_degree": j.tolist(),
                "calibrated_utc": now.isoformat(),
                "expires_utc": (now + timedelta(hours=2)).isoformat(),
                "validation": {
                    "holdout_error_px": residual,
                    "return_limit_px": 2,
                    "opposing_response_limit_px_per_degree": 1.5,
                    "purpose": "25 px dead-zone angular centering; not grasp-position calibration",
                    "basis": "Static-scene flow; direction/gain only, not hand depth",
                },
            }
            save(ROOT / "local/hand-follow.json", profile)
            record["result"] = "hand_response_measured_returned_to_anchor"
            return record
    except BaseException as exc:
        record.update(result="aborted_no_automatic_recovery", error=str(exc))
        raise
    finally:
        save(path, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--space-clear", action="store_true")
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("X", "Y", "WIDTH", "HEIGHT"),
        help="Native sensor pixels of inspected stationary scene",
    )
    parser.add_argument(
        "--exclude-roi", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            calibrate(args.execute, args.space_clear, args.roi, args.exclude_roi),
            indent=2,
        )
    )
