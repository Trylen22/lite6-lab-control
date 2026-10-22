"""One supervised new-location pick through a checked fixed-height corridor.

This extends the small repeat experiment by MEASURING the current image response
and checking each observed displacement during transit. It does not simply relax
the old repeat guard. The operator must confirm clear arm/travel space. Defaults
are read-only; no enable, mode change, fault reset or indefinite retry exists.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from .calibration import fit_response
from .calibration_motion import CalibrationArm, ROOT
from .contact_pick import search_contact
from .cycle_return import return_to_observation
from .green_calibrate import FOLDER, observe, save
from .motion_profile import validate_speed_scale
from scripts.taught_pick_trial import perform_cycle


def correction_in_corridor(pose, delta, start, destination, margin=10):
    """Check the explicitly previewed XY corridor; keep Z/RPY fixed throughout."""
    target = pose.copy()
    target[:2] = (np.array(pose[:2]) + delta).tolist()
    lower = np.minimum(start[:2], destination[:2]) - margin
    upper = np.maximum(start[:2], destination[:2]) + margin
    if (
        not np.all(np.isfinite(target))
        or np.any(np.array(target[:2]) < lower)
        or np.any(np.array(target[:2]) > upper)
    ):
        raise RuntimeError("Target leaves the checked transit corridor")
    if not np.allclose(target[2:], start[2:], atol=0.3, rtol=0):
        raise RuntimeError("Transit height/orientation changed")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--space-clear",
        action="store_true",
        help="Operator confirmed this new travel space is clear",
    )
    parser.add_argument("--speed-scale", type=float, default=1)
    parser.add_argument(
        "--reference-trial",
        type=Path,
        required=True,
        help="Fresh successful local seal/lift/release record",
    )
    parser.add_argument(
        "--resume-measurements",
        action="store_true",
        help="Fresh checked return from a declared measurement checkpoint",
    )
    parser.add_argument(
        "--response-from",
        type=Path,
        help="Reuse fresh measured response with matching camera and live marker origin",
    )
    args = parser.parse_args()
    validate_speed_scale(args.speed_scale)
    if args.execute and not args.space_clear:
        parser.error("Execution requires operator-confirmed clear travel space")
    plan = json.loads((FOLDER / "extended-region-plan.json").read_text())
    relocation = json.loads((FOLDER / "relocation.json").read_text())
    teaching = json.loads((FOLDER / "teaching.json").read_text())
    reference = json.loads(args.reference_trial.read_text())
    if reference["result"] not in {
        "repeat_completed_release_io_verified",
        "new_location_pick_completed_release_io_verified",
        "single_pick_completed_release_io_verified",
    }:
        raise RuntimeError("Requires a completed seal/lift/release reference")
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(reference["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 1800:
        raise RuntimeError("Contact reference older than 30 minutes; inspect again")
    successful = [
        e["pose"]
        for e in reference["events"]
        if e["event"] == "contact_checkpoint" and e["sealed"]
    ]
    floor_z = successful[-1][2]
    aim = np.array(
        [e for e in teaching["events"] if e["event"] == "guide_observation"][-1][
            "observation"
        ]["center_px"]
    )
    expected_start = plan["lateral_preview"]["start"]
    destination = plan["lateral_preview"]["target"]
    old_j = np.array(relocation["original_model"]["jacobian_px_per_mm"])
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "execute": args.execute,
        "space_clear_confirmed": args.space_clear,
        "speed_scale": args.speed_scale,
        "contact_floor_z_mm": floor_z,
        "cup_aim_px": aim.tolist(),
        "events": [],
    }
    path = (
        ROOT
        / "local/trial_logs"
        / datetime.now(timezone.utc).strftime("retarget-green-%Y%m%dT%H%M%S.json")
    )

    def observation():
        ob = observe()
        if (
            ob["session"] != relocation["camera_session"]
            or ob["resolution"] != relocation["resolution"]
        ):
            raise RuntimeError("Camera context differs from reference")
        return ob

    try:
        with CalibrationArm() as robot:
            start = robot.check()
            resumed = False
            if not np.allclose(start, expected_start, atol=0.25, rtol=0):
                checkpoints = []
                for dx, dy in [(5, 0), (-5, 0), (0, 5), (0, -5), (3, 3)]:
                    point = expected_start.copy()
                    point[0] += dx
                    point[1] += dy
                    checkpoints.append(point)
                if not args.resume_measurements or not any(
                    np.allclose(start, point, atol=0.25, rtol=0)
                    for point in checkpoints
                ):
                    raise RuntimeError(
                        "Arm changed outside the declared measurement checkpoints"
                    )
                record["measurement_resume_pose"] = start
                resumed = True
            watch = teaching["watch_pose"]
            if not np.allclose(start[2:], watch[2:], atol=0.3, rtol=0):
                raise RuntimeError("Not at calibrated observation height/orientation")
            initial = observation()
            record.update(
                start=start,
                initial_observation=initial,
                transit_preview=robot.preview(destination),
            )
            print(json.dumps(record, indent=2), flush=True)
            if not args.execute:
                record["result"] = "read_only_plan"
                return
            if resumed:
                # Explicit fresh preflight and a planned high return, not an
                # exception-handler recovery move. Unknown poses are refused.
                robot.move(expected_start, speed=5 * args.speed_scale)
                start = robot.check()
            if args.response_from:
                cached = json.loads(args.response_from.read_text())
                response_age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(cached["captured_utc"])
                ).total_seconds()
                if not 0 <= response_age <= 600:
                    raise RuntimeError("Measured response older than ten minutes")
                samples = cached["response_samples"]
                if any(
                    item["session"] != relocation["camera_session"]
                    or item["resolution"] != relocation["resolution"]
                    for item in samples
                ):
                    raise RuntimeError("Cached response camera context differs")
                measured = fit_response(
                    [item["offset_mm"] for item in samples],
                    [item["center_px"] for item in samples],
                )
                j = np.array(measured["jacobian_px_per_mm"])
                holdout_error = cached["holdout_error_px"]
                if (
                    holdout_error > 2
                    or np.linalg.norm(j - old_j) / np.linalg.norm(old_j) > 0.2
                ):
                    raise RuntimeError("Cached response validation failed")
                current_marker = observation()
                if (
                    np.linalg.norm(
                        np.array(current_marker["center_px"]) - measured["aim_px"]
                    )
                    > 3
                ):
                    raise RuntimeError("Marker differs from measured origin")
                record.update(
                    response_samples=samples,
                    measured_response=measured,
                    holdout_error_px=holdout_error,
                    reused_response=args.response_from.name,
                )
            else:
                samples = []
                for offset in [(0, 0), (5, 0), (-5, 0), (0, 5), (0, -5), (0, 0)]:
                    target = correction_in_corridor(
                        start, np.array(offset), start, destination
                    )
                    if not np.allclose(robot.check(), target, atol=0.2, rtol=0):
                        robot.move(target, speed=5 * args.speed_scale)
                    ob = observation()
                    samples.append({"offset_mm": list(offset), **ob})
                    record["response_samples"] = samples
                    save(path, record)
                if (
                    np.linalg.norm(
                        np.array(samples[0]["center_px"]) - samples[-1]["center_px"]
                    )
                    > 2
                ):
                    raise RuntimeError("Marker moved during local response measurement")
                measured = fit_response(
                    [s["offset_mm"] for s in samples], [s["center_px"] for s in samples]
                )
                j = np.array(measured["jacobian_px_per_mm"])
                if np.linalg.norm(j - old_j) / np.linalg.norm(old_j) > 0.2:
                    raise RuntimeError(
                        "Measured response differs too much from reference"
                    )
                target = correction_in_corridor(
                    start, np.array([3, 3]), start, destination
                )
                robot.move(target, speed=5 * args.speed_scale)
                holdout = observation()
                predicted = np.array(measured["aim_px"]) + j @ np.array([3, 3])
                holdout_error = float(np.linalg.norm(predicted - holdout["center_px"]))
                if holdout_error > 2:
                    raise RuntimeError("Independent response check exceeds two pixels")
                robot.move(start, speed=5 * args.speed_scale)
                record.update(
                    measured_response=measured, holdout_error_px=holdout_error
                )
            ob = observation()
            estimate = np.array(start[:2]) + np.linalg.solve(j, aim - ob["center_px"])
            if np.max(np.abs(estimate - destination[:2])) > 10:
                raise RuntimeError(
                    "New response puts target outside previewed pickup area"
                )
            travel = 0
            for iteration in range(35):
                pose = robot.check()
                correction_in_corridor(pose, np.zeros(2), start, destination)
                error = np.linalg.solve(j, aim - ob["center_px"])
                record["events"].append(
                    {
                        "event": "tracking_observation",
                        "iteration": iteration,
                        "pose": pose,
                        "observation": ob,
                        "estimated_error_mm": error.tolist(),
                    }
                )
                save(path, record)
                print(
                    "Tracking",
                    iteration,
                    "estimated correction mm",
                    error.tolist(),
                    flush=True,
                )
                if np.linalg.norm(error) <= 0.75:
                    break
                delta = error * 0.6
                if np.linalg.norm(delta) > 5:
                    delta *= 5 / np.linalg.norm(delta)
                travel += np.linalg.norm(delta)
                if travel > 140:
                    raise RuntimeError("Transit travel budget reached")
                target = correction_in_corridor(pose, delta, start, destination)
                robot.move(target, speed=5 * args.speed_scale)
                new_ob = observation()
                observed = np.array(new_ob["center_px"]) - ob["center_px"]
                response_error = float(np.linalg.norm(observed - j @ delta))
                record["events"].append(
                    {"event": "response_check", "residual_px": response_error}
                )
                if response_error > 3:
                    raise RuntimeError(
                        "Image movement inconsistent with measured response"
                    )
                if (
                    np.linalg.norm(aim - new_ob["center_px"])
                    > np.linalg.norm(aim - ob["center_px"]) + 2
                ):
                    raise RuntimeError("Marker moving away from the cup guide")
                ob = new_ob
            else:
                raise RuntimeError("Tracking iteration limit")
            aligned = robot.check()
            correction_in_corridor(aligned, np.zeros(2), start, destination)
            low = aligned.copy()
            low[2] = floor_z
            # The measured destination is an estimate, not a pickup coordinate.
            # Check the actual aligned descent independently before any lowering.
            record["descent_preview"] = robot.preview(low)
            save(path, record)
            above = low.copy()
            above[2] += 5
            robot.move(above, speed=5 * args.speed_scale)
            contact = search_contact(
                robot.arm, above, record["events"], speed_scale=args.speed_scale
            )
            if contact is None:
                record["final_pose"] = robot.check()
                record["result"] = "no_seal_at_unchanged_floor_released_no_lift"
                return
            lift = contact.copy()
            lift[2] += 10
            release = contact.copy()
            release[2] += 2
            perform_cycle(
                robot.arm,
                contact,
                lift,
                record["events"],
                release_pose=release,
                speed_scale=args.speed_scale,
            )
            record["release_pose"] = robot.check()
            record["final_pose"] = return_to_observation(
                robot, watch[2], 5 * args.speed_scale, record["events"]
            )
            record["result"] = "new_location_pick_completed_release_io_verified"
            teaching.update(
                status="retarget_completed_at_observation_height",
                last_pose=record["final_pose"],
                latest_contact_pose=contact,
            )
            save(FOLDER / "teaching.json", teaching)
    except BaseException as exc:
        record.update(result="aborted_no_automatic_recovery", error=str(exc))
        raise
    finally:
        save(path, record)
        print("Record:", path, flush=True)


if __name__ == "__main__":
    main()
