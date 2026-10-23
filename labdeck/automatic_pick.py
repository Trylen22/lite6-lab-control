"""One UI-requested green pick, using the validated local tabletop profile.

The dashboard dispatches this worker; telemetry never invokes it. Opening a page
or importing this module cannot move hardware. All machine-specific geometry
comes from ignored local/automation.json, not request-supplied coordinates.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import numpy as np

from .calibration_motion import CalibrationArm, ROOT
from .contact_pick import search_contact
from .cycle_return import return_to_observation
from .green_calibrate import observe, save
from .motion_profile import (
    validate_speed_scale,
    clear_travel_speed,
    CLEARANCE_ABOVE_FLOOR_MM,
)
from scripts.taught_pick_trial import perform_cycle

PROFILE = ROOT / "local/automation.json"


def load_profile(path=PROFILE):
    """Validate stored scope before a worker can even connect to the arm."""
    profile = json.loads(Path(path).read_text())
    if profile.get("schema") != 1:
        raise ValueError("No supported pickup profile; validate calibration first")
    validate_speed_scale(profile["speed_scale"])
    clear_travel_speed(profile)
    j = np.array(profile["jacobian_px_per_mm"], dtype=float)
    if (
        j.shape != (2, 2)
        or not np.isfinite(j).all()
        or np.linalg.cond(j) > 5
        or min(np.linalg.svd(j, compute_uv=False)) < 0.25
    ):
        raise ValueError("Invalid image response calibration")
    lo = np.array(profile["xy_min_mm"], dtype=float)
    hi = np.array(profile["xy_max_mm"], dtype=float)
    if (
        lo.shape != (2,)
        or hi.shape != (2,)
        or not np.isfinite([lo, hi]).all()
        or np.any(lo >= hi)
    ):
        raise ValueError("Invalid checked tabletop bounds")
    for region in profile.get("xy_regions_mm", []):
        bounds = np.array(region, dtype=float)
        if (
            bounds.shape != (2, 2)
            or not np.isfinite(bounds).all()
            or np.any(bounds[0] >= bounds[1])
            or np.any(bounds[0] < lo)
            or np.any(bounds[1] > hi)
        ):
            raise ValueError("Invalid checked workspace subregion")
    h = profile["observation_height_mm"]
    floor = profile["contact_floor_z_mm"]
    if (
        not np.isfinite([h, floor]).all()
        or not 200 <= h <= 350
        or not 5 < h - floor < 250
    ):
        raise ValueError("Invalid taught height/contact floor")
    rpy = np.array(profile["orientation_degrees"], dtype=float)
    aim = np.array(profile["cup_aim_px"], dtype=float)
    if (
        rpy.shape != (3,)
        or aim.shape != (2,)
        or not np.isfinite(rpy).all()
        or not np.isfinite(aim).all()
    ):
        raise ValueError("Invalid wrist/aim reference")
    if (
        profile["resolution"] != [640, 400]
        or np.any(aim < 12)
        or np.any(aim > np.array([640, 400]) - 12)
    ):
        raise ValueError("Invalid camera context")
    return profile


def check_observation_pose(pose, profile):
    """The fixed-height mapping cannot be reused after arbitrary manual jogging."""
    if abs(pose[2] - profile["observation_height_mm"]) > 0.3 or not np.allclose(
        pose[3:], profile["orientation_degrees"], atol=0.3, rtol=0
    ):
        raise RuntimeError(
            "Return to the calibrated camera height and wrist orientation"
        )
    xy = np.array(pose[:2])
    regions = profile.get("xy_regions_mm") or [
        [profile["xy_min_mm"], profile["xy_max_mm"]]
    ]
    if not any(np.all(xy >= lo) and np.all(xy <= hi) for lo, hi in regions):
        raise RuntimeError("Outside the checked tabletop region")


def check_transit(start, target, profile):
    """An allowed endpoint cannot authorize crossing a gap between regions."""
    count = max(1, int(np.ceil(np.linalg.norm(np.array(target[:2]) - start[:2]))))
    for fraction in np.linspace(0, 1, count + 1):
        check_observation_pose(
            (np.array(start) + fraction * (np.array(target) - start)).tolist(), profile
        )


class CycleEvents(list):
    """Translate audited controller events into UI progress, not motion commands."""

    LABELS = {
        "contact_checkpoint": ("sealing", "Checking suction attachment"),
        "attachment_feedback_confirmed": ("lifting", "Seal confirmed"),
        "lift_to_taught_approach": ("lifting", "Lifting 10 mm"),
        "hold_started": ("holding", "Holding for two seconds"),
        "lower_to_verified_release_clearance": ("placing", "Lowering the block"),
        "release_io_verified": ("releasing", "Release verified"),
        "return_to_observation_started": ("returning", "Returning to camera height"),
        "returned_to_observation": ("returning", "Camera height reached"),
    }

    def __init__(self, progress):
        super().__init__()
        self.progress = progress
        self.started_monotonic = time.monotonic()

    def append(self, event):
        event.setdefault("elapsed_seconds", time.monotonic() - self.started_monotonic)
        super().append(event)
        if event["event"] in self.LABELS:
            phase, message = self.LABELS[event["event"]]
            super().append(
                {
                    "event": "phase_started",
                    "phase": phase,
                    "message": message,
                    "elapsed_seconds": event["elapsed_seconds"],
                }
            )
            self.progress(phase, message)


def run_cycle(
    profile_path=PROFILE, progress=lambda *_: None, min_area=100, execute=False
):
    """Full preflight per click. One cycle, bounded motion, no enable/reset/retry."""
    if type(min_area) is not int or not 100 <= min_area <= 10000:
        raise ValueError("Invalid detection area")
    profile = load_profile(profile_path)
    j = np.array(profile["jacobian_px_per_mm"])
    aim = np.array(profile["cup_aim_px"])
    scale = profile["speed_scale"]
    travel_speed = clear_travel_speed(profile)
    events = CycleEvents(progress)
    report_progress = progress

    def progress(phase, message):
        # Monotonic phase boundaries permit comparisons without wall-clock jumps.
        events.append({"event": "phase_started", "phase": phase, "message": message})
        report_progress(phase, message)

    record = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile["profile_id"],
        "execute": execute,
        "speed_scale": scale,
        "clear_travel_mm_s": travel_speed,
        "min_area": min_area,
        "events": events,
    }
    path = (
        ROOT
        / "local/trial_logs"
        / datetime.now(timezone.utc).strftime("button-pick-%Y%m%dT%H%M%S.json")
    )

    def fresh_target():
        ob = observe(min_area=min_area)
        # Same camera, same mount: a restarted camera program (new session
        # ID) does not change the optics, so only the image format is checked.
        if ob["resolution"] != profile["resolution"]:
            raise RuntimeError("Camera resolution changed; revalidate calibration")
        return ob

    try:
        progress("checking", "Checking robot, tool and calibration")
        with CalibrationArm() as robot:
            start = robot.check()
            check_observation_pose(start, profile)
            progress("detecting", "Finding one stable green marker")
            ob = fresh_target()
            estimate = start.copy()
            estimate[:2] = (
                np.array(start[:2]) + np.linalg.solve(j, aim - ob["center_px"])
            ).tolist()
            check_transit(start, estimate, profile)
            predicted_low = estimate.copy()
            predicted_low[2] = profile["contact_floor_z_mm"]
            record.update(
                start=start,
                initial_observation=ob,
                initial_path_preview=robot.preview(estimate),
                predicted_pick_path=robot.preview_path(
                    [estimate, predicted_low, estimate]
                ),
            )
            if not execute:
                record["result"] = "read_only_preflight_passed"
                return record
            travel = 0
            for iteration in range(35):
                pose = robot.check()
                check_observation_pose(pose, profile)
                error = np.linalg.solve(j, aim - ob["center_px"])
                events.append(
                    {
                        "event": "tracking_observation",
                        "pose": pose,
                        "observation": ob,
                        "error_mm": error.tolist(),
                    }
                )
                progress(
                    "aligning",
                    f"Aligning green marker · {np.linalg.norm(error):.1f} mm remaining",
                )
                save(path, record)
                if np.linalg.norm(error) <= 0.75:
                    break
                delta = error * 0.6
                if np.linalg.norm(delta) > 5:
                    delta *= 5 / np.linalg.norm(delta)
                travel += np.linalg.norm(delta)
                if travel > 140:
                    raise RuntimeError("Alignment travel limit reached")
                target = pose.copy()
                target[:2] = (np.array(pose[:2]) + delta).tolist()
                check_transit(pose, target, profile)
                robot.move(target, speed=5 * scale)
                updated = fresh_target()
                residual = float(
                    np.linalg.norm(
                        np.array(updated["center_px"]) - ob["center_px"] - j @ delta
                    )
                )
                events.append({"event": "response_check", "residual_px": residual})
                if residual > 3:
                    raise RuntimeError("Image movement disagrees with calibration")
                if (
                    np.linalg.norm(aim - updated["center_px"])
                    > np.linalg.norm(aim - ob["center_px"]) + 2
                ):
                    raise RuntimeError("Target moved away during alignment")
                ob = updated
            else:
                raise RuntimeError("Alignment iteration limit reached")
            low = robot.check()
            low[2] = profile["contact_floor_z_mm"]
            record["descent_preview"] = robot.preview(low)
            progress("approaching", "Approaching above the block")
            above = low.copy()
            above[2] += 5
            if travel_speed > 5 * scale:
                # Accelerate only well above contact. The final 10 mm approach
                # retains its demonstrated speed; suction/search starts at +5.
                clearance = low.copy()
                clearance[2] += CLEARANCE_ABOVE_FLOOR_MM
                robot.move(clearance, speed=travel_speed)
                progress("approaching", "Slow approach above the block")
            robot.move(above, speed=5 * scale)
            progress("sealing", "Suction on before final approach")
            contact = search_contact(robot.arm, above, events, speed_scale=scale)
            if contact is None:
                raise RuntimeError(
                    "No seal at the depth limit; suction released, no lift"
                )
            lift = contact.copy()
            lift[2] += 10
            release = contact.copy()
            release[2] += 2
            perform_cycle(
                robot.arm,
                contact,
                lift,
                events,
                release_pose=release,
                speed_scale=scale,
            )
            record["release_pose"] = robot.check()
            if travel_speed > 5 * scale:
                # Independently recheck release before the slow initial retreat.
                # Only the subsequent empty-tool return uses the increased rate.
                clearance = record["release_pose"].copy()
                clearance[2] = low[2] + CLEARANCE_ABOVE_FLOOR_MM
                progress("returning", "Clearing the block at slow speed")
                robot.move(clearance, speed=5 * scale)
            record["final_pose"] = return_to_observation(
                robot, profile["observation_height_mm"], travel_speed, events
            )
            record["result"] = "completed_at_observation_height_release_verified"
            progress("complete", "Pick & Place complete · back at camera height")
            return record
    except BaseException as exc:
        record.update(result="aborted_no_automatic_recovery", error=str(exc))
        raise
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        record["total_seconds"] = time.monotonic() - events.started_monotonic
        phases = [e for e in events if e["event"] == "phase_started"]
        timings = {}
        for index, event in enumerate(phases):
            end = (
                phases[index + 1]["elapsed_seconds"]
                if index + 1 < len(phases)
                else record["total_seconds"]
            )
            timings[event["phase"]] = (
                timings.get(event["phase"], 0) + end - event["elapsed_seconds"]
            )
        record["phase_seconds"] = timings
        save(path, record)
