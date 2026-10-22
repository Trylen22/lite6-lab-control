"""One supervised, calibrated green pick. Default is a read-only plan.

This first classroom experiment is restricted to the SAME stationary block,
height and small XY region used for calibration. No general table searching,
new object heights, gestures or retries. A failed seal never authorizes a deeper
contact. The operator must watch the approach with the physical E-stop ready.
"""

import argparse
from datetime import datetime, timezone
import json

import numpy as np

from .calibration_motion import CalibrationArm, ROOT
from .green_calibrate import MODEL, SEED, observe, same_context, save
from scripts.taught_pick_trial import perform_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--block-unchanged",
        action="store_true",
        help="Operator confirmed block stayed at the taught contact location",
    )
    args = parser.parse_args()
    if not args.block_unchanged:
        parser.error(
            "Requires physical confirmation of unchanged block/contact reference"
        )
    model = json.loads(MODEL.read_text())
    seed = json.loads(SEED.read_text())
    if model["seed"] != seed or model["status"] != "align_only_validated":
        raise RuntimeError("No matching validated XY calibration")
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(model["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 1800:
        raise RuntimeError("Calibration older than 30 minutes; inspect/recalibrate")
    events = []
    record = {
        "executed": args.execute,
        "events": events,
        "operator_confirmed_block_unchanged": True,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with CalibrationArm() as robot:
            start = robot.check()
            same_context(start, seed)
            observation = observe()
            if (
                observation["session"] != model["session"]
                or observation["resolution"] != model["resolution"]
            ):
                raise RuntimeError("Camera context changed")
            error = np.linalg.solve(
                model["jacobian_px_per_mm"],
                np.array(model["aim_px"]) - observation["center_px"],
            )
            if np.linalg.norm(error) > 0.75:
                raise RuntimeError("Not aligned; use align stage first")
            contact = start.copy()
            contact[2] = seed["contact_reference"][2]
            # No depth estimation or extrapolated contact height: use only the
            # previously sealed floor, same block and same table. Wrist angle
            # must remain within the small measured deviation from that teaching.
            if not np.allclose(
                contact[3:], seed["contact_reference"][3:], atol=0.3, rtol=0
            ):
                raise RuntimeError("Wrist differs from taught contact")
            hover = contact.copy()
            hover[2] += 10
            release = contact.copy()
            release[2] += 2
            plan = robot.preview(contact)
            record.update(
                plan=plan,
                observation=observation,
                alignment_error_mm=error.tolist(),
                contact_floor=contact,
                lift_pose=hover,
                release_pose=release,
            )
            print(json.dumps(record, indent=2), flush=True)
            if not args.execute:
                record["result"] = "read_only_plan"
                return
            # High approach stays on one fixed XY line; short completed segments
            # allow a fresh health/tool/camera check before each next command.
            targets = list(np.arange(start[2] - 20, hover[2], -20)) + [hover[2]]
            for z in targets:
                target = start.copy()
                target[2] = float(z)
                robot.move(target)
                events.append({"event": "approach_checkpoint", "pose": robot.check()})
            # Final 10 mm is deliberately slower. Never descend below the known
            # sealed floor, and never activate suction during this positioning.
            for z in np.arange(hover[2] - 2, contact[2] - 1, -2):
                target = contact.copy()
                target[2] = max(float(z), contact[2])
                robot.move(target, speed=2)
            robot.check()
            # Reuse the tested single-cycle seal gate and corrected release I/O.
            # Exceptions at contact release the tool; uncertain poses preserve
            # tool state for operator recovery. No automatic repeat is attempted.
            perform_cycle(robot.arm, contact, hover, events, release_pose=release)
            robot.check()
            record["result"] = "cycle_completed_release_io_verified"
            print(
                "Single calibrated pick completed; stopped at 2 mm release clearance",
                flush=True,
            )
    except BaseException as exc:
        record["result"] = "aborted_no_automatic_recovery"
        record["error"] = str(exc)
        raise
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        path = (
            ROOT
            / "local/trial_logs"
            / datetime.now(timezone.utc).strftime("vision-pick-%Y%m%dT%H%M%S.json")
        )
        save(path, record)
        print("Record:", path, flush=True)


if __name__ == "__main__":
    main()
