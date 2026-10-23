"""Wrist-joint calibration for the puppy demo.

The image Jacobian depends on how the camera is mounted, not on the clock, so
it does not expire. Recalibrate if the camera mount or demo pose changes.
"""

import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "local/hand-follow.json"


def load_hand_profile(path=PROFILE):
    p = json.loads(Path(path).read_text())
    if p.get("hand_schema") != 2:
        raise ValueError("Calibrate the wrist-follow pose first")
    if p["joint_axes"] != [3, 4]:
        raise ValueError("Only wrist joints 4 and 5 are allowed")
    anchor = np.array(p["anchor_joints_deg"], dtype=float)
    j = np.array(p["jacobian_px_per_degree"], dtype=float)
    bounds = np.array([p["joint_min_deg"], p["joint_max_deg"]], dtype=float)
    if anchor.shape != (6,) or not np.isfinite(anchor).all():
        raise ValueError("Invalid wrist anchor")
    if (
        j.shape != (2, 2)
        or not np.isfinite(j).all()
        or np.linalg.cond(j) > 5
        or min(np.linalg.svd(j, compute_uv=False)) < 0.5
    ):
        raise ValueError("Invalid wrist image response")
    if (
        bounds.shape != (2, 2)
        or not np.isfinite(bounds).all()
        or np.any(bounds[0] >= bounds[1])
        or np.any(bounds[1] - bounds[0] > 12)
        or np.any(anchor[[3, 4]] < bounds[0])
        or np.any(anchor[[3, 4]] > bounds[1])
    ):
        raise ValueError("Invalid wrist bounds")
    if not p["camera_session"] or p["resolution"] != [640, 400]:
        raise ValueError("Invalid camera context")
    return p


def check_hand_pose(joints, p):
    actual = np.array(joints, dtype=float)
    anchor = np.array(p["anchor_joints_deg"])
    if (
        actual.shape != (6,)
        or not np.isfinite(actual).all()
        or not np.allclose(
            actual[[0, 1, 2, 5]], anchor[[0, 1, 2, 5]], atol=0.15, rtol=0
        )
    ):
        raise RuntimeError("Base/shoulder or wrist-roll changed; recalibrate hand pose")
    if np.any(actual[[3, 4]] < p["joint_min_deg"]) or np.any(
        actual[[3, 4]] > p["joint_max_deg"]
    ):
        raise RuntimeError("Wrist-follow boundary reached")


def check_hand_transit(start, target, p):
    check_hand_pose(start, p)
    check_hand_pose(target, p)
