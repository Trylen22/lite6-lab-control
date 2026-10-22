"""Approach a manually relocated block, stopping ABOVE historical contact.

This establishes a new teaching opportunity, not a pickup. The preserved image
reticle is a guide at the same camera height/orientation. We correct only small
placement error, then stop 10 mm above the previous sealed contact floor. The
operator must inspect and teach actual new contact separately. No tool commands,
new contact claims, blind retries or below-clearance movements are allowed.
"""

import argparse
from datetime import datetime, timezone
import json

import numpy as np

from .calibration import correction_mm
from .calibration_motion import CalibrationArm
from .green_calibrate import FOLDER, observe, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    relocation_path = FOLDER / "relocation.json"
    relocation = json.loads(relocation_path.read_text())
    if relocation["status"] != "awaiting_operator_block_placement":
        raise RuntimeError("Not at the stationary block placement handoff")
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(relocation["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 1800:
        raise RuntimeError("Relocation older than 30 minutes; inspect again")
    model = relocation["original_model"]
    anchor = relocation["actual_pose"]
    trace = []
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "executed": args.execute,
        "operator_reported_block_placed": True,
        "contact_verified": False,
        "events": trace,
        "status": "plan_only",
    }
    path = FOLDER / "teaching.json"
    try:
        with CalibrationArm() as robot:
            if not np.allclose(robot.check(), anchor, atol=0.3, rtol=0):
                raise RuntimeError("Arm moved since placement handoff")
            for iteration in range(6):
                pose = robot.check()
                if not np.allclose(pose[2:], anchor[2:], atol=0.3, rtol=0):
                    raise RuntimeError(
                        "Height/orientation changed during guide alignment"
                    )
                if max(abs(pose[i] - anchor[i]) for i in [0, 1]) > 5:
                    raise RuntimeError(
                        "Teaching alignment exceeds 5 mm placement region"
                    )
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
                if np.linalg.norm(error) > 5:
                    raise RuntimeError(
                        "Block too far from guide; operator must reposition"
                    )
                trace.append(
                    {
                        "event": "guide_observation",
                        "pose": pose,
                        "observation": obs,
                        "estimated_error_mm": error.tolist(),
                    }
                )
                if np.linalg.norm(error) <= 0.75:
                    break
                delta = correction_mm(model, obs["center_px"])
                target = pose.copy()
                target[:2] = (np.array(pose[:2]) + delta).tolist()
                if max(abs(target[i] - anchor[i]) for i in [0, 1]) > 5:
                    raise RuntimeError("Correction would leave placement region")
                if not args.execute:
                    record["first_correction_mm"] = delta
                    print(json.dumps(record, indent=2))
                    return
                robot.move(target)
                save(path, record)
            else:
                raise RuntimeError("Guide alignment iteration limit")
            watch = robot.check()
            clearance = watch.copy()
            clearance[2] = model["seed"]["contact_reference"][2] + 10
            if not 10 <= watch[2] - clearance[2] <= 200:
                raise RuntimeError("Approach outside bounded height range")
            record.update(
                watch_pose=watch,
                clearance_pose=clearance,
                historical_contact_floor_mm=model["seed"]["contact_reference"][2],
                approach_plan=robot.preview(clearance),
            )
            print(json.dumps(record, indent=2), flush=True)
            if not args.execute:
                return
            relocation["status"] = "teaching_approach_started"
            save(relocation_path, relocation)
            record["status"] = "approaching_clearance"
            save(path, record)
            # No suction and no contact search. At most 20 mm per checkpoint,
            # with the final 20 mm slower. Stop above the historical floor.
            zs = list(np.arange(watch[2] - 20, clearance[2], -20)) + [clearance[2]]
            for z in zs:
                target = clearance.copy()
                target[2] = float(z)
                robot.move(target, speed=2 if z - clearance[2] < 20 else 5)
                trace.append({"event": "clearance_checkpoint", "pose": robot.check()})
                save(path, record)
            record["status"] = "awaiting_operator_contact_inspection"
            print(
                "Idle above historical contact. No suction or contact claim.",
                flush=True,
            )
    except BaseException as exc:
        record.update(status="aborted_no_automatic_recovery", error=str(exc))
        raise
    finally:
        save(path, record)


if __name__ == "__main__":
    main()
