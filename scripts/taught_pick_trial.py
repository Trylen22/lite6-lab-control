#!/usr/bin/env python3
"""Bounded operator-taught suction trials. Default: read-only preflight.

This is NOT vision-guided picking. Contact/approach records came from the
operator's manual teaching at one unchanged block position. No Cartesian
position is inferred from the camera or manufacturer dimensions.

Run only with the operator at the physical emergency stop and the taught block
still in place. --execute explicitly permits this single bounded cycle; there
is no repeat loop and no UI motion route.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
import tomllib

from xarm.wrapper import XArmAPI

# Direct script execution places scripts/ first; add the project package root.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labdeck.suction import checked_vacuum
from labdeck.motion_profile import validate_speed_scale

ROOT = Path(__file__).resolve().parents[1]


def validate_geometry(contact, approach):
    """Reject moved/rotated or long paths rather than generalizing a taught trial."""
    low = contact["pose_mm_degrees"]
    high = approach["pose_mm_degrees"]
    if len(low) != 6 or len(high) != 6 or not all(math.isfinite(v) for v in low + high):
        raise ValueError("Expected six finite pose values")
    if not contact.get("contact_observed_by_operator"):
        raise ValueError("Contact has not been observed by the operator")
    if any(abs(low[i] - high[i]) > 0.05 for i in (0, 1, 3, 4, 5)):
        raise ValueError(
            "Trial allows vertical translation only, with unchanged orientation"
        )
    if not 0.5 <= high[2] - low[2] <= 2.1:
        raise ValueError("Trial lift must be between 0.5 and 2.1 mm")
    return low, high


def require_zero(code, operation):
    if code != 0:
        raise RuntimeError(f"{operation} returned SDK code {code}; aborting")


def read_value(result, operation):
    code, value = result
    require_zero(code, operation)
    return value


def perform_cycle(
    arm,
    low,
    high,
    record,
    sleep=time.sleep,
    release_at_hover=False,
    start_pose=None,
    release_pose=None,
    speed_scale=1.0,
):
    """Execute on an already checked arm; fake-arm tests exercise failure paths.

    Optional release_at_hover implements the operator-requested small drop: it
    releases only after reaching the bounded <=2.1 mm hover and completing the
    monitored hold. It never descends into a compressed contact pose.

    The explicit pickup10 profile starts at the verified 2 mm clearance,
    returns to the already verified contact, lifts 10 mm, and releases only
    after lowering to that clearance. These are fixed vertical waypoints.

    Suction feedback must indicate attachment before any lifting. On failure,
    suction is released ONLY when we know we are at the taught supported contact.
    If a movement/feedback check fails away from contact, preserve the tool state
    and require operator recovery instead of blindly descending or dropping.
    """
    validate_speed_scale(speed_scale)
    at_contact = start_pose is None
    suction_started = False

    def event(name, **details):
        record.append(
            {
                "time_utc": datetime.now(timezone.utc).isoformat(),
                "event": name,
                **details,
            }
        )
        print(name, details, flush=True)

    def healthy():
        errors = read_value(arm.get_err_warn_code(), "read errors")
        state = read_value(arm.get_state(), "read state")
        if errors != [0, 0] or state not in (0, 1, 2):
            raise RuntimeError(
                f"Controller not healthy: state={state}, errors={errors}"
            )

    def confirm_pose(target):
        pose = read_value(arm.get_position(), "read reached pose")
        if any(abs(pose[i] - target[i]) > 0.5 for i in range(6)):
            raise RuntimeError(
                "Reached pose differs from taught target by more than tolerance"
            )
        return pose

    def release_tool(operation):
        # The manufacturer's OFF state is DO0=0, DO1=1. Leave release asserted.
        # Clearing DO1 to zero was an unvalidated assumption and was removed
        # after the operator reported incomplete shutoff. Verify I/O, not sound.
        require_zero(
            checked_vacuum(arm, False, wait=False, sync=False, sleep=sleep), operation
        )
        for _ in range(20):
            sleep(0.1)
            outputs = read_value(
                arm.get_tgpio_output_digital(), "release output readback"
            )
            inputs = read_value(arm.get_tool_digital_input(), "release pickup input")
            if outputs == [0, 1, 0, 0, 0] and inputs[0] == 0:
                event("release_io_verified", outputs=outputs, inputs=inputs)
                return
        raise RuntimeError(
            "Release I/O not confirmed; no completion claim or further movement"
        )

    def move(target, name):
        healthy()
        event(name, target=target, speed_mm_s=2 * speed_scale, acceleration_mm_s2=5)
        require_zero(
            arm.set_position(
                *target,
                speed=2 * speed_scale,
                mvacc=5,
                is_radian=False,
                wait=True,
                timeout=10,
            ),
            name,
        )
        confirm_pose(target)
        healthy()

    try:
        healthy()
        confirm_pose(start_pose if start_pose is not None else low)
        if start_pose is not None:
            # Return only along the previously demonstrated 2 mm vertical path.
            # No suction is active during this positioning step.
            move(low, "return_to_verified_contact")
            at_contact = True
        suction_started = True  # A partially successful I/O command also needs cleanup.
        event("suction_on")
        require_zero(
            checked_vacuum(arm, True, wait=True, timeout=2, sync=False, sleep=sleep),
            "confirm suction",
        )
        attached = read_value(arm.get_vacuum_gripper(), "read vacuum feedback")
        if attached != 1:
            raise RuntimeError(
                f"No confirmed attachment; feedback={attached}; no lift permitted"
            )
        event("attachment_feedback_confirmed")
        # Mark uncertain before sending motion: a timeout does not establish
        # whether the arm stayed at contact, reached its target, or stopped midway.
        at_contact = False
        move(high, "lift_to_taught_approach")
        event("hold_started", seconds=2)
        # Inspect health/seal during the hold, rather than sleeping blindly.
        for _ in range(20):
            sleep(0.1)
            healthy()
            if read_value(arm.get_vacuum_gripper(), "hold vacuum feedback") != 1:
                raise RuntimeError(
                    "Attachment feedback lost during hold; operator recovery required"
                )
        if release_pose is not None:
            move(release_pose, "lower_to_verified_release_clearance")
            event(
                "release_at_verified_clearance", clearance_mm=release_pose[2] - low[2]
            )
        elif release_at_hover:
            healthy()
            confirm_pose(high)
            event(
                "release_at_authorized_small_hover",
                drop_upper_bound_mm=high[2] - low[2],
            )
        else:
            move(low, "lower_to_taught_contact")
            at_contact = True
            event("release_at_supported_contact")
        release_tool("release suction")
        suction_started = False
        event(
            "cycle_complete_at_hover"
            if release_at_hover or release_pose is not None
            else "cycle_complete_at_contact"
        )
    except Exception:
        if suction_started and at_contact:
            # Cleanup at contact is allowed only after a fresh pose confirms
            # support and a health check confirms the controller has no stop/fault.
            try:
                healthy()
                confirm_pose(low)
                release_tool("contact cleanup release")
                event("aborted_at_contact_tool_released")
            except Exception as cleanup_error:
                event(
                    "cleanup_not_confirmed_operator_recovery", error=str(cleanup_error)
                )
        else:
            event("aborted_pose_uncertain_preserve_tool_for_operator")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", required=True, type=Path)
    parser.add_argument("--approach", required=True, type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run ONE taught cycle; otherwise inspect only",
    )
    parser.add_argument(
        "--release-at-hover",
        action="store_true",
        help="Explicit small-drop variant: release at <=2.1 mm hover, without descending",
    )
    parser.add_argument(
        "--pickup-10mm",
        action="store_true",
        help="Explicit profile: start at 2 mm clearance, contact, lift 10 mm, hold, return to clearance, release",
    )
    args = parser.parse_args()
    if args.pickup_10mm and args.release_at_hover:
        parser.error("pickup-10mm releases at the low clearance, not at the 10 mm lift")
    contact = json.loads(args.contact.read_text())
    approach = json.loads(args.approach.read_text())
    low, high = validate_geometry(contact, approach)
    start_pose = None
    release_pose = None
    if args.pickup_10mm:
        if abs(high[2] - low[2] - 2) > 0.05:
            parser.error("pickup-10mm requires the verified 2 mm clearance record")
        start_pose = high.copy()
        release_pose = high.copy()
        high = low.copy()
        high[2] += 10.0
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(contact["captured_utc"])
    ).total_seconds()
    if age < 0 or age > 900:
        raise SystemExit("Contact record is older than 15 minutes; teach/inspect again")
    config = tomllib.loads((ROOT / "local/lab.toml").read_text())
    reference = json.loads(
        (ROOT / "local/taught_poses/controller-tool-report.json").read_text()
    )
    received = threading.Event()
    arm = XArmAPI(
        config["robot"]["ip"],
        do_not_open=True,
        enable_report=True,
        report_type="rich",
        timed_comm=False,
    )
    arm.register_report_callback(lambda *_: received.set())
    events = []
    outcome = {
        "executed": args.execute,
        "release_at_hover": args.release_at_hover,
        "pickup_10mm": args.pickup_10mm,
        "contact_file": args.contact.name,
        "approach_file": args.approach.name,
        "events": events,
    }
    try:
        arm.connect()
        if not received.wait(4):
            raise RuntimeError("No live rich robot report")
        received.clear()
        if not received.wait(2):
            raise RuntimeError("No second live rich robot report")
        if arm.mode != 0 or arm.state != 2 or not all(arm.motor_enable_states[:6]):
            raise RuntimeError(
                "Requires already-enabled, idle position mode; no enable/reset will be issued"
            )
        if arm.is_simulation_robot:
            raise RuntimeError("Controller reports simulation mode")
        if arm.collision_sensitivity < 3:
            raise RuntimeError(
                "Collision sensitivity below observed reference; no change attempted"
            )
        for actual, expected in (
            (arm.tcp_offset, reference["tcp_offset_mm_degrees"]),
            (arm.world_offset, reference["world_offset_mm_degrees"]),
        ):
            if any(abs(a - b) > 0.001 for a, b in zip(actual, expected)):
                raise RuntimeError("Controller offsets changed since teaching")
        if arm.tcp_load != reference["tcp_load_kg_and_cog_mm"]:
            raise RuntimeError("Configured tool load changed since inspection")
        if read_value(arm.get_cmdnum(), "read queue depth") != 0:
            raise RuntimeError("Other commands queued; refusing to compete with Studio")
        pose = read_value(arm.get_position(), "preflight pose")
        expected_start = start_pose if start_pose is not None else low
        if any(abs(pose[i] - expected_start[i]) > 0.25 for i in range(6)):
            raise RuntimeError("Arm has moved away from the verified starting pose")
        outputs = read_value(arm.get_tgpio_output_digital(), "read tool outputs")
        if outputs != [0, 1, 0, 0, 0]:
            raise RuntimeError("Requires manufacturer OFF/release state: DO0=0, DO1=1")
        if read_value(arm.get_tool_digital_input(), "preflight pickup input")[0] != 0:
            raise RuntimeError("Pickup input remains asserted before the trial")
        outcome["preflight"] = {
            "pose": pose,
            "tcp_offset": arm.tcp_offset,
            "load": arm.tcp_load,
            "lift_mm": high[2] - low[2],
            "start_pose": start_pose,
            "release_pose": release_pose,
        }
        print(json.dumps(outcome["preflight"], indent=2), flush=True)
        if args.execute:
            perform_cycle(
                arm,
                low,
                high,
                events,
                release_at_hover=args.release_at_hover,
                start_pose=start_pose,
                release_pose=release_pose,
            )
        outcome["result"] = "completed" if args.execute else "preflight_only_passed"
    except Exception as exc:
        outcome["result"] = "aborted"
        outcome["error"] = str(exc)
        raise
    finally:
        arm.disconnect()
        folder = ROOT / "local/trial_logs"
        folder.mkdir(exist_ok=True)
        path = folder / datetime.now(timezone.utc).strftime("trial-%Y%m%dT%H%M%S.json")
        path.write_text(json.dumps(outcome, indent=2) + "\n")
        print("Trial record:", path, flush=True)


if __name__ == "__main__":
    main()
