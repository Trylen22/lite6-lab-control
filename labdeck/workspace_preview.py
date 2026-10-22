"""Read-only reachability preview for the visible block's candidate corridor.

Run with ``python -m labdeck.workspace_preview``. Nothing here moves the robot,
changes the active profile, or detects shelf geometry. Operator inspection is
still required for the complete arm/camera swept volume. Sampled IK feasibility
is different from physical clearance or measured pickup repeatability.
"""

from datetime import datetime, timezone
import json

import numpy as np

from .automatic_pick import check_observation_pose, load_profile
from .calibration_motion import CalibrationArm, ROOT
from .green_calibrate import observe, save


def preview_extension(min_area=200):
    profile = load_profile()
    observation = observe(min_area=min_area)
    if (
        observation["session"] != profile["camera_session"]
        or observation["resolution"] != profile["resolution"]
    ):
        raise RuntimeError("Camera context changed")
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "observation": observation,
        "checks": [],
        "result": "incomplete",
    }
    path = ROOT / "local/calibration/workspace-extension-preview.json"
    try:
        with CalibrationArm() as robot:
            start = robot.check()
            check_observation_pose(start, profile)
            estimate = start.copy()
            estimate[:2] = (
                np.array(start[:2])
                + np.linalg.solve(
                    profile["jacobian_px_per_mm"],
                    np.array(profile["cup_aim_px"]) - observation["center_px"],
                )
            ).tolist()
            # A 10 mm margin allows bounded corrections near the predicted
            # endpoint. It does not authorize the whole visible tabletop.
            lo = (np.minimum(start[:2], estimate[:2]) - 10).tolist()
            hi = (np.maximum(start[:2], estimate[:2]) + 10).tolist()
            record.update(start=start, estimate=estimate, candidate_region=[lo, hi])
            for x in np.linspace(lo[0], hi[0], 3):
                for y in np.linspace(lo[1], hi[1], 3):
                    high = start.copy()
                    high[:2] = [float(x), float(y)]
                    low = high.copy()
                    low[2] = profile["contact_floor_z_mm"]
                    print("Preview XY:", high[:2], flush=True)
                    record["checks"].append(
                        robot.preview_path([high, low, high, start])
                    )
            low = estimate.copy()
            low[2] = profile["contact_floor_z_mm"]
            record["target_path"] = robot.preview_path([estimate, low, estimate, start])
            record["result"] = "read_only_ik_grid_passed_not_obstacle_detection"
            return record
    except BaseException as exc:
        record.update(result="failed_no_motion", error=str(exc))
        raise
    finally:
        save(path, record)


if __name__ == "__main__":
    result = preview_extension()
    print(
        json.dumps(
            {"result": result["result"], "candidate_region": result["candidate_region"]}
        )
    )
