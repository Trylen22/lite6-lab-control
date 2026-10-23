"""Record a hand-guided path, read-only, at ~10 Hz.

The operator moves the arm (Studio manual mode / jog) while this script only
READS joints and TCP pose. It never enables, moves, changes mode or touches
tool I/O. Each sample is one JSON line: monotonic time, joints (deg),
pose (mm, deg). Stop with Ctrl+C / SIGTERM, or after --max-seconds.

Usage: .venv/bin/python scripts/record_path.py --name shelf
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time
import tomllib

from xarm.wrapper import XArmAPI

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="path")
    parser.add_argument("--hz", type=float, default=10)
    parser.add_argument("--max-seconds", type=float, default=600)
    args = parser.parse_args()
    config = tomllib.loads((ROOT / "local/lab.toml").read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = ROOT / f"local/taught_poses/{args.name}-path-{stamp}.jsonl"
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    arm = XArmAPI(
        config["robot"]["ip"], do_not_open=True, enable_report=False, timed_comm=False
    )
    arm.connect()
    print(f"Recording to {out}", flush=True)
    started = time.monotonic()
    count = 0
    try:
        with out.open("w") as file:
            while not stop and time.monotonic() - started < args.max_seconds:
                tick = time.monotonic()
                code_j, joints = arm.get_servo_angle()
                code_p, pose = arm.get_position()
                if code_j == 0 and code_p == 0:
                    file.write(
                        json.dumps(
                            {
                                "t": round(tick - started, 3),
                                "joints": [round(x, 3) for x in joints[:6]],
                                "pose": [round(x, 2) for x in pose],
                            }
                        )
                        + "\n"
                    )
                    file.flush()
                    count += 1
                time.sleep(max(0, 1 / args.hz - (time.monotonic() - tick)))
    finally:
        arm.disconnect()
        print(f"Stopped after {count} samples", flush=True)


if __name__ == "__main__":
    main()
