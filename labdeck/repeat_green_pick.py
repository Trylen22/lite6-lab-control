"""Return to the new observation pose and repeat ONE checked green pick.

The operator confirmed the first relocated lift and requested a repeat with
15 percent faster movement and continuous vertical approaches. No indefinite
loop, extra compression, contact search extension, mode change or fault reset.
The final approach remains slow and never passes the newly sealed contact floor.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from .contact_pick import search_contact
from .calibration import correction_mm
from .calibration_motion import CalibrationArm, ROOT, value
from .green_calibrate import FOLDER, observe, save
from scripts.taught_pick_trial import perform_cycle


def retry_seal(failed_path, execute, speed_scale):
    """One changed-sequence retry at the SAME floor; default read-only plan."""
    failed = json.loads(failed_path.read_text())
    if (
        failed.get("result") != "aborted_no_automatic_recovery"
        or failed.get("error") != "confirm suction returned SDK code 41; aborting"
    ):
        raise RuntimeError("Retry accepts only the recorded no-attachment timeout")
    if not any(
        event["event"] == "aborted_at_contact_tool_released"
        for event in failed["events"]
    ):
        raise RuntimeError("No verified stationary release after failed seal")
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(failed["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 600:
        raise RuntimeError("Failed contact reference older than ten minutes")
    floor = failed["descent_plan"]["target"]
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "execute": execute,
        "retry_of": failed_path.name,
        "sequence_change": "Suction on before final descent",
        "same_floor_pose": floor,
        "speed_scale": speed_scale,
        "events": [],
    }
    path = (
        ROOT
        / "local/trial_logs"
        / datetime.now(timezone.utc).strftime("repeat-seal-retry-%Y%m%dT%H%M%S.json")
    )
    try:
        with CalibrationArm() as robot:
            actual = robot.check()
            above = floor.copy()
            above[2] += 5
            if not (
                np.allclose(actual, floor, atol=0.25, rtol=0)
                or np.allclose(actual, above, atol=0.25, rtol=0)
            ):
                raise RuntimeError(
                    "Arm is neither at failed contact nor its verified 5 mm clearance"
                )
            record["starting_pose"] = actual
            record["retract_plan"] = robot.preview(above)
            print(json.dumps(record, indent=2), flush=True)
            if not execute:
                record["result"] = "read_only_retry_plan"
                return
            # Retract with tool OFF, establish ON I/O while stationary, and then
            # search automatically in small increments without passing the floor.
            if not np.allclose(actual, above, atol=0.25, rtol=0):
                robot.move(above, speed=2 * speed_scale)
            contact = search_contact(
                robot.arm, above, record["events"], speed_scale=speed_scale
            )
            if contact is None:
                record["final_pose"] = robot.check()
                record["result"] = "no_seal_at_same_floor_released_no_lift"
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
                speed_scale=speed_scale,
            )
            record["final_pose"] = robot.check()
            record["result"] = "repeat_completed_release_io_verified"
            teaching = json.loads((FOLDER / "teaching.json").read_text())
            teaching.update(
                status="repeat_completed_waiting_physical_release",
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--speed-scale", type=float, default=1)
    parser.add_argument(
        "--retry-from",
        type=Path,
        help="Explicit fresh failed-seal record; one same-floor changed-sequence retry",
    )
    args = parser.parse_args()
    if not 1 <= args.speed_scale <= 1.15:
        parser.error("Speed scale must be 1.0 through the authorized 1.15")
    if args.retry_from is not None:
        retry_seal(args.retry_from, args.execute, args.speed_scale)
        return
    teaching = json.loads((FOLDER / "teaching.json").read_text())
    contact_record = json.loads((FOLDER / "relocated-contact.json").read_text())
    relocation = json.loads((FOLDER / "relocation.json").read_text())
    if (
        teaching["status"] != "contact_seal_and_pick_verified_waiting_physical_release"
        or not contact_record["seal_feedback_verified"]
    ):
        raise RuntimeError("Requires the completed first relocated seal/pick trial")
    age = (
        datetime.now(timezone.utc)
        - datetime.fromisoformat(contact_record["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 900:
        raise RuntimeError("Contact reference older than 15 minutes; re-inspect")
    watch = teaching["watch_pose"]
    floor_z = contact_record["pose_mm_degrees"][2]
    # The final pre-contact observation was taken at the XY that subsequently
    # sealed and lifted. It is the measured image anchor for this NEW cup pose.
    anchor = [
        event for event in teaching["events"] if event["event"] == "guide_observation"
    ][-1]
    model = {
        **relocation["original_model"],
        "aim_px": anchor["observation"]["center_px"],
    }
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "execute": args.execute,
        "speed_scale": args.speed_scale,
        "operator_confirmed_first_lift_release": True,
        "events": [],
        "new_contact_floor_z_mm": floor_z,
    }
    path = (
        ROOT
        / "local/trial_logs"
        / datetime.now(timezone.utc).strftime("repeat-green-%Y%m%dT%H%M%S.json")
    )
    try:
        with CalibrationArm() as robot:
            start = robot.check()
            if not np.allclose(start, teaching["last_pose"], atol=0.25, rtol=0):
                raise RuntimeError("Arm moved since the completed pickup")
            record["return_plan"] = robot.preview(watch)
            print(json.dumps(record, indent=2), flush=True)
            if not args.execute:
                record["result"] = "read_only_return_plan"
                return
            teaching["status"] = "repeat_started"
            save(FOLDER / "teaching.json", teaching)
            # One continuous vertical return replaces the earlier 20 mm stops.
            robot.move(watch, speed=5 * args.speed_scale)
            for iteration in range(6):
                pose = robot.check()
                if (
                    not np.allclose(pose[2:], watch[2:], atol=0.3, rtol=0)
                    or max(abs(pose[i] - watch[i]) for i in [0, 1]) > 5
                ):
                    raise RuntimeError("Outside fixed-height local repeat region")
                obs = observe()
                if (
                    obs["session"] != relocation["camera_session"]
                    or obs["resolution"] != relocation["resolution"]
                ):
                    raise RuntimeError("Camera context changed")
                error = np.linalg.solve(
                    model["jacobian_px_per_mm"],
                    np.array(model["aim_px"]) - obs["center_px"],
                )
                record["events"].append(
                    {
                        "event": "repeat_observation",
                        "pose": pose,
                        "observation": obs,
                        "error_mm": error.tolist(),
                    }
                )
                save(path, record)
                if np.linalg.norm(error) > 5:
                    raise RuntimeError("Block moved beyond the bounded repeat region")
                if np.linalg.norm(error) <= 0.75:
                    break
                delta = correction_mm(model, obs["center_px"])
                target = pose.copy()
                target[:2] = (np.array(pose[:2]) + delta).tolist()
                if max(abs(target[i] - watch[i]) for i in [0, 1]) > 5:
                    raise RuntimeError("Correction exceeds local region")
                robot.move(target, speed=5 * args.speed_scale)
            else:
                raise RuntimeError("Repeat alignment iteration limit")
            low = robot.check()
            low[2] = floor_z
            record["descent_plan"] = robot.preview(low)
            save(path, record)
            # A continuous high approach, followed by one continuous slow final
            # 5 mm. This reduces pauses without speeding contact by several-fold.
            above = low.copy()
            above[2] += 5
            robot.move(above, speed=5 * args.speed_scale)
            # Preserve the successful ordering: suction BEFORE final descent.
            # The feedback checkpoints are automatic, not operator pauses, and
            # the 5 mm search floor is exactly the already sealed contact Z.
            contact = search_contact(
                robot.arm, above, record["events"], speed_scale=args.speed_scale
            )
            if contact is None:
                robot.check()
                raise RuntimeError("No seal at the known floor; released, no lift")
            low = contact
            lift = low.copy()
            lift[2] += 10
            release = low.copy()
            release[2] += 2
            perform_cycle(
                robot.arm,
                low,
                lift,
                record["events"],
                release_pose=release,
                speed_scale=args.speed_scale,
            )
            record["final_pose"] = robot.check()
            record["tool_outputs"] = value(robot.arm.get_tgpio_output_digital())
            record["pickup_inputs"] = value(robot.arm.get_tool_digital_input())
            record["result"] = "repeat_completed_release_io_verified"
            teaching.update(
                status="repeat_completed_waiting_physical_release",
                last_pose=record["final_pose"],
                latest_contact_pose=low,
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
