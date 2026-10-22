"""One supervised contact search and pick after operator gap inspection.

The operator estimated a 5 mm gap at the relocated block. That estimate permits
at most 5 mm of slow vertical search, NOT a general contact detector or a deeper
retry. Suction feedback must establish attachment before any lift. A failed
search releases in place; a fault/uncertain pose preserves state for recovery.
"""

import argparse
from datetime import datetime, timezone
import json
import time

import numpy as np

from .calibration_motion import CalibrationArm, ROOT, value
from .suction import checked_vacuum
from .motion_profile import validate_speed_scale
from .green_calibrate import FOLDER, save
from scripts.taught_pick_trial import perform_cycle


def search_contact(arm, start, events, sleep=time.sleep, speed_scale=1.0):
    """Testable bounded search: 0.5 mm increments, 0.5 mm/s, total <=5 mm.

    This function is called ONLY after live tool-OFF preflight and a complete
    IK preview. While pump is on, the release-only calibration wrapper cannot
    be used: explicitly check ON I/O, health, pose and seal at each checkpoint.
    There is no force sensing claim; the operator-defined floor is mandatory.
    """

    validate_speed_scale(speed_scale)

    def healthy_on():
        if value(arm.get_err_warn_code()) != [0, 0] or value(arm.get_state()) != 2:
            raise RuntimeError("Controller not healthy and idle during contact search")
        if value(arm.get_tgpio_output_digital()) != [1, 0, 0, 0, 0]:
            raise RuntimeError("Unexpected suction ON outputs")
        if value(arm.get_cmdnum()) != 0:
            raise RuntimeError("Another command queued during contact search")

    def released():
        code = checked_vacuum(arm, False, wait=False, sync=False, sleep=sleep)
        if code != 0:
            raise RuntimeError(f"Release command failed: {code}")
        for _ in range(20):
            sleep(0.1)
            if (
                value(arm.get_tgpio_output_digital()) == [0, 1, 0, 0, 0]
                and value(arm.get_tool_digital_input())[0] == 0
            ):
                events.append({"event": "search_release_io_verified"})
                return
        raise RuntimeError("Search release I/O not verified")

    expected = start.copy()
    pose_known = True
    try:
        code = checked_vacuum(arm, True, wait=False, sync=False, sleep=sleep)
        if code != 0:
            raise RuntimeError(f"Suction ON failed: {code}")
        # The SDK writes two outputs separately. A command ACK does not mean
        # both outputs have settled. Stay stationary and require final ON state
        # within one second before allowing the first search movement.
        for _ in range(10):
            sleep(0.1)
            if value(arm.get_state()) != 2 or value(arm.get_err_warn_code()) != [0, 0]:
                raise RuntimeError("Controller changed during suction transition")
            outputs = value(arm.get_tgpio_output_digital())
            events.append({"event": "suction_transition_readback", "outputs": outputs})
            if outputs == [1, 0, 0, 0, 0]:
                break
        else:
            raise RuntimeError("Suction ON outputs did not settle; no search move")
        for index in range(11):
            healthy_on()
            pose = value(arm.get_position())
            if not np.allclose(pose, expected, atol=0.2, rtol=0):
                pose_known = False
                raise RuntimeError("Contact checkpoint pose uncertain")
            # Require three consecutive seal reports at a stationary checkpoint.
            sealed = True
            for _ in range(3):
                sleep(0.1)
                healthy_on()
                if (
                    value(arm.get_tool_digital_input())[0] != 1
                    or value(arm.get_vacuum_gripper()) != 1
                ):
                    sealed = False
            events.append(
                {"event": "contact_checkpoint", "pose": pose, "sealed": sealed}
            )
            print(events[-1], flush=True)
            if sealed:
                if not np.allclose(value(arm.get_position()), pose, atol=0.2, rtol=0):
                    pose_known = False
                    raise RuntimeError("Pose changed during seal confirmation")
                return pose
            if index == 10:
                released()
                return None
            expected = start.copy()
            expected[2] -= 0.5 * (index + 1)
            pose_known = False  # A timeout does not establish where motion ended.
            code = arm.set_position(
                *expected,
                speed=0.5 * speed_scale,
                mvacc=2,
                is_radian=False,
                wait=True,
                timeout=5,
            )
            if code != 0:
                raise RuntimeError(f"Contact step returned {code}; no recovery move")
            actual = value(arm.get_position())
            if not np.allclose(actual, expected, atol=0.2, rtol=0):
                raise RuntimeError("Contact step did not reach its bounded target")
            pose_known = True
    except BaseException:
        # Release only when a fresh healthy check establishes we are stationary
        # at the known supported-search checkpoint. Never move as cleanup.
        if pose_known:
            try:
                if (
                    value(arm.get_state()) == 2
                    and value(arm.get_err_warn_code()) == [0, 0]
                    and np.allclose(
                        value(arm.get_position()), expected, atol=0.2, rtol=0
                    )
                ):
                    released()
            except BaseException as exc:
                events.append({"event": "cleanup_unconfirmed", "error": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    teaching = json.loads((FOLDER / "teaching.json").read_text())
    if teaching["status"] != "awaiting_operator_contact_inspection":
        raise RuntimeError(
            "Requires completed clearance approach and fresh operator inspection"
        )
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(teaching["captured_utc"])
    ).total_seconds()
    if not 0 <= age <= 900:
        raise RuntimeError("Clearance inspection older than 15 minutes")
    record = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "executed": args.execute,
        "operator_observation": "Basically centered, not touching, approximately 5 mm to contact",
        "maximum_search_mm": 5,
        "events": [],
    }
    path = (
        ROOT
        / "local/trial_logs"
        / datetime.now(timezone.utc).strftime("contact-pick-%Y%m%dT%H%M%S.json")
    )
    try:
        with CalibrationArm() as robot:
            start = robot.check()
            if not np.allclose(start, teaching["clearance_pose"], atol=0.25, rtol=0):
                raise RuntimeError("Arm moved since clearance inspection")
            floor = start.copy()
            floor[2] -= 5
            high = start.copy()
            high[2] += 10
            record.update(
                start=start,
                search_preview=robot.preview(floor),
                lift_preview=robot.preview(high),
            )
            print(json.dumps(record, indent=2), flush=True)
            if not args.execute:
                record["result"] = "read_only_plan"
                return
            teaching["status"] = "contact_search_started"
            save(FOLDER / "teaching.json", teaching)
            contact = search_contact(robot.arm, start, record["events"])
            if contact is None:
                robot.check()
                record["result"] = "no_seal_stopped_released_no_lift"
                teaching["status"] = "search_limit_reached_operator_inspection_needed"
                teaching["last_pose"] = robot.check()
                save(FOLDER / "teaching.json", teaching)
                print(
                    "No seal within 5 mm; stopped and release verified. No lift.",
                    flush=True,
                )
                return
            contact_record = {
                "captured_utc": datetime.now(timezone.utc).isoformat(),
                "pose_mm_degrees": contact,
                "contact_observed_by_operator": False,
                "contact_established_by_seal_feedback": True,
                "operator_statement": "Supervised centered approach, 5 mm bounded search",
                "seal_feedback_verified": True,
                "source": "Three consecutive DI0/vacuum feedback assertions",
            }
            save(FOLDER / "relocated-contact.json", contact_record)
            lift = contact.copy()
            lift[2] += 10
            release = contact.copy()
            release[2] += 2
            perform_cycle(
                robot.arm, contact, lift, record["events"], release_pose=release
            )
            robot.check()
            record["result"] = "single_pick_completed_release_io_verified"
            teaching["status"] = (
                "contact_seal_and_pick_verified_waiting_physical_release"
            )
            teaching["contact_pose"] = contact
            teaching["last_pose"] = robot.check()
            save(FOLDER / "teaching.json", teaching)
    except BaseException as exc:
        record.update(result="aborted_no_automatic_recovery", error=str(exc))
        raise
    finally:
        save(path, record)
        print("Record:", path, flush=True)


if __name__ == "__main__":
    main()
