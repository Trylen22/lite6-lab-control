#!/usr/bin/env python3
"""A stationary suction diagnostic: inspect by default, pulse only with --pulse.

No movement, enable, mode change, or fault-reset API is called here. The default
vacuum feedback and all available Lite 6 tool inputs are logged together so a
missing seal can be distinguished from a possible feedback-mapping issue.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import tomllib

from xarm.wrapper import XArmAPI

ROOT = Path(__file__).resolve().parents[1]


def read(result):
    code, value = result
    if code != 0:
        raise RuntimeError(f"SDK query returned {code}")
    return value


def require_zero(code):
    if code != 0:
        raise RuntimeError(f"SDK command returned {code}")


def sample(arm):
    return {
        "pose": read(arm.get_position()),
        "state": read(arm.get_state()),
        "errors": read(arm.get_err_warn_code()),
        "vacuum": read(arm.get_vacuum_gripper()),
        "inputs": read(arm.get_tool_digital_input()),
        "outputs": read(arm.get_tgpio_output_digital()),
    }


def pulse(arm, expected, samples, seconds=2.0, sleep=time.sleep):
    """Pulse at a checked stationary pose, always ending in a release/off attempt."""
    baseline = sample(arm)
    samples.append({"phase": "before", **baseline})
    if (
        baseline["state"] != 2
        or baseline["errors"] != [0, 0]
        or any(baseline["outputs"])
    ):
        raise RuntimeError(
            "Requires idle/error-free controller and all tool outputs low"
        )
    if any(abs(a - b) > 0.25 for a, b in zip(baseline["pose"], expected)):
        raise RuntimeError("Pose changed since the stationary inspection")
    if read(arm.get_cmdnum()) != 0:
        raise RuntimeError("Other commands are queued")
    try:
        require_zero(arm.set_vacuum_gripper(True, wait=False, sync=False))
        for tick in range(round(seconds * 10)):
            sleep(0.1)
            result = sample(arm)
            samples.append(
                {"phase": "on", "nominal_seconds": (tick + 1) / 10, **result}
            )
            if result["state"] != 2 or result["errors"] != [0, 0]:
                raise RuntimeError(
                    "Controller state changed during the stationary test"
                )
            if any(abs(a - b) > 0.25 for a, b in zip(result["pose"], expected)):
                raise RuntimeError("Arm position changed during stationary test")
    finally:
        # No lift occurs in this diagnostic. End suction, briefly allow the
        # release output, then return both outputs to the all-low baseline.
        require_zero(arm.set_vacuum_gripper(False, wait=False, sync=False))
        sleep(0.3)
        require_zero(arm.set_tgpio_digital(1, 0, sync=False))
        samples.append({"phase": "after", **sample(arm)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pulse", action="store_true")
    parser.add_argument("--pose-record", type=Path)
    args = parser.parse_args()
    if args.pulse and not args.pose_record:
        parser.error("--pulse requires a fresh inspected --pose-record")
    config = tomllib.loads((ROOT / "local/lab.toml").read_text())
    arm = XArmAPI(
        config["robot"]["ip"], do_not_open=True, enable_report=False, timed_comm=False
    )
    result = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "pulse_requested": args.pulse,
        "samples": [],
    }
    try:
        arm.connect()
        if args.pulse:
            inspection = json.loads(args.pose_record.read_text())
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(inspection["captured_utc"])
            ).total_seconds()
            if not 0 <= age < 300:
                raise RuntimeError(
                    "Stationary pose inspection must be less than five minutes old"
                )
            pulse(arm, inspection["poses"][-1], result["samples"])
        else:
            result["samples"].append({"phase": "read_only", **sample(arm)})
        result["result"] = "completed"
    except BaseException as exc:
        result["result"] = "aborted"
        result["error"] = str(exc)
        raise
    finally:
        arm.disconnect()
        folder = ROOT / "local/trial_logs"
        folder.mkdir(exist_ok=True)
        path = folder / datetime.now(timezone.utc).strftime(
            "suction-diagnostic-%Y%m%dT%H%M%S.json"
        )
        path.write_text(json.dumps(result, indent=2) + "\n")
        print("Diagnostic log:", path, flush=True)
        for row in result["samples"]:
            print(
                row["phase"],
                "vacuum=",
                row["vacuum"],
                "inputs=",
                row["inputs"],
                "outputs=",
                row["outputs"],
                flush=True,
            )


if __name__ == "__main__":
    main()
