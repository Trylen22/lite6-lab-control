"""Supervised green-marker calibration. Nothing moves without --execute.

Stages are deliberately separate: raise vertically, sample a small XY square,
then align at observation height. This module NEVER descends or operates suction.
Run from the project root with python -m labdeck.green_calibrate STAGE.
"""

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

import cv2
import numpy as np

from .calibration import correction_mm, fit_response
from .calibration_motion import CalibrationArm, ROOT
from .color import detect_color

FOLDER = ROOT / "local/calibration"
SEED = FOLDER / "seed.json"
MODEL = FOLDER / "green.json"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def observe():
    """Three distinct, post-settle frames, one unambiguous stable green candidate.

    Monotonic clocks are shared because producer and consumer run on this host.
    A new camera process changes session ID and invalidates the observation.
    """
    after = time.monotonic() + 0.3
    previous = None
    centers = []
    session = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with urllib.request.urlopen(
            "http://127.0.0.1:8090/observation.json", timeout=1
        ) as response:
            item = json.load(response)
        if not item["fresh"] or item["age_seconds"] > 0.5:
            raise RuntimeError("Camera stale")
        if session is not None and session != item["session"]:
            raise RuntimeError("Camera restarted during observation")
        session = item["session"]
        if item["received_monotonic"] <= after or item["sequence"] == previous:
            time.sleep(0.04)
            continue
        previous = item["sequence"]
        image = cv2.imdecode(
            np.frombuffer(base64.b64decode(item["jpeg_base64"]), np.uint8),
            cv2.IMREAD_COLOR,
        )
        candidates, _ = detect_color(image, "green", min_area=100)
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one green candidate, found {len(candidates)}")
        x, y, w, h = candidates[0]["bbox"]
        if min(x, y, image.shape[1] - x - w, image.shape[0] - y - h) < 12:
            raise RuntimeError("Target too close to image edge")
        centers.append(candidates[0]["center"])
        if len(centers) == 3:
            if np.ptp(np.array(centers), axis=0).max() > 2:
                raise RuntimeError("Marker unstable across three fresh frames")
            return {
                "center_px": np.mean(centers, axis=0).tolist(),
                "session": session,
                "sequence": previous,
                "resolution": [image.shape[1], image.shape[0]],
            }
    raise RuntimeError("No stable fresh observation")


def same_context(pose, seed):
    watch = seed["watch_pose"]
    if not np.allclose(np.array(pose)[2:], np.array(watch)[2:], atol=0.3, rtol=0):
        raise RuntimeError("Height/orientation differs from calibration")
    if np.max(np.abs(np.array(pose[:2]) - watch[:2])) > 10.3:
        raise RuntimeError("Outside measured +/-10 mm XY workspace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["raise", "adopt-watch", "sample", "probe", "align", "observe"]
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--z", type=float, default=180, help="Vertical observation height, robot mm"
    )
    parser.add_argument(
        "--contact",
        type=Path,
        help="Operator-taught local contact JSON; required for first raise",
    )
    args = parser.parse_args()
    FOLDER.mkdir(exist_ok=True)
    if args.stage == "observe":
        print(json.dumps(observe(), indent=2))
        return
    with CalibrationArm() as robot:
        start = robot.check()
        if args.stage == "raise":
            # The historical operator-taught contact is evidence, not renewed
            # permission to descend. Only the known released clearance can seed.
            if not SEED.exists():
                if args.contact is None:
                    parser.error(
                        "First raise requires --contact with the operator-taught record"
                    )
                contact_path = args.contact
                teaching = json.loads(contact_path.read_text())
                if not teaching.get("contact_observed_by_operator"):
                    raise RuntimeError("No operator-observed contact reference")
                contact = teaching["pose_mm_degrees"]
                clearance = contact.copy()
                clearance[2] += 2
                if not np.allclose(start, clearance, atol=0.25, rtol=0):
                    raise RuntimeError(
                        "Not at the verified released clearance; re-teach"
                    )
            else:
                prior = json.loads(SEED.read_text())
                contact = prior["contact_reference"]
                contact_path = Path(prior["contact_source"])
                if not np.allclose(start, prior["watch_pose"], atol=0.3, rtol=0):
                    raise RuntimeError("Moved since previous vertical stage")
            if not start[2] < args.z <= 280:
                raise RuntimeError("Raise must be upward and <=280 mm")
            target = start.copy()
            target[2] = args.z
            print(json.dumps(robot.preview(target), indent=2), flush=True)
            if args.execute:
                # Small completed segments leave observable checkpoints and avoid
                # a long blocking command. No XY displacement or wrist rotation.
                for z in np.arange(start[2] + 20, args.z + 20, 20):
                    waypoint = target.copy()
                    waypoint[2] = min(float(z), args.z)
                    robot.move(waypoint)
                    save(
                        SEED,
                        {
                            "captured_utc": datetime.now(timezone.utc).isoformat(),
                            "watch_pose": robot.check(),
                            "contact_reference": contact,
                            "contact_source": contact_path.name,
                            "release_confirmed_by_operator": True,
                            "note": "Contact reference is historical; no descent validated by this stage.",
                        },
                    )
            return
        seed = json.loads(SEED.read_text())
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(seed["captured_utc"])
        ).total_seconds()
        if not 0 <= age <= 3600:
            raise RuntimeError("Calibration seed older than one hour; re-inspect setup")
        if args.stage == "adopt-watch":
            # Accept operator vertical jogging only. This reads/records; no move.
            previous = seed["watch_pose"]
            if not np.allclose(
                np.array(start)[[0, 1, 3, 4, 5]],
                np.array(previous)[[0, 1, 3, 4, 5]],
                atol=0.3,
                rtol=0,
            ):
                raise RuntimeError(
                    "Manual jog changed XY/orientation; re-teach aiming relationship"
                )
            observation = observe()
            seed.update(
                watch_pose=start,
                captured_utc=datetime.now(timezone.utc).isoformat(),
                initial_observation=observation,
                note="Operator-jogged observation pose, unchanged taught XY; aiming reference remains provisional until contact recheck.",
            )
            save(SEED, seed)
            print(json.dumps(seed, indent=2))
            return
        same_context(start, seed)
        origin = seed["watch_pose"]
        if args.stage == "sample":
            if not np.allclose(start, origin, atol=0.3, rtol=0):
                raise RuntimeError("Sampling must start at raised taught XY reference")
            offsets = [
                (0, 0),
                (10, 0),
                (10, 10),
                (0, 10),
                (-10, 10),
                (-10, 0),
                (-10, -10),
                (0, -10),
                (10, -10),
                (0, 0),
            ]
            print(
                "Sampling plan: 20 mm square, fixed height/orientation; tool remains OFF",
                flush=True,
            )
            if not args.execute:
                print(json.dumps(observe(), indent=2))
                return
            MODEL.unlink(missing_ok=True)
            samples = []
            for offset in offsets:
                target = origin.copy()
                target[0] += offset[0]
                target[1] += offset[1]
                if not np.allclose(robot.check(), target, atol=0.3, rtol=0):
                    robot.move(target)
                observation = observe()
                robot.check()
                samples.append({"offset_mm": list(offset), **observation})
                save(FOLDER / "samples.json", samples)
                print("Observed", samples[-1], flush=True)
                if (
                    observation["session"] != samples[0]["session"]
                    or observation["resolution"] != samples[0]["resolution"]
                ):
                    raise RuntimeError("Camera context changed during calibration")
            if (
                np.linalg.norm(
                    np.array(samples[0]["center_px"]) - samples[-1]["center_px"]
                )
                > 2
            ):
                raise RuntimeError("Target moved or return-to-origin inconsistent")
            model = fit_response(
                [s["offset_mm"] for s in samples], [s["center_px"] for s in samples]
            )
            # Independent interior positions were not used to fit J.
            validations = []
            for offset in [(5, 5), (-5, -5), (0, 0)]:
                target = origin.copy()
                target[0] += offset[0]
                target[1] += offset[1]
                robot.move(target)
                obs = observe()
                if (
                    obs["session"] != samples[0]["session"]
                    or obs["resolution"] != samples[0]["resolution"]
                ):
                    raise RuntimeError("Camera changed during validation")
                predicted = (
                    np.array(model["aim_px"])
                    + np.array(model["jacobian_px_per_mm"]) @ offset
                )
                error = float(np.linalg.norm(predicted - obs["center_px"]))
                validations.append({"offset_mm": list(offset), "error_px": error})
                if error > 2:
                    raise RuntimeError("Independent validation exceeds two pixels")
            save(
                MODEL,
                {
                    **model,
                    "seed": seed,
                    "session": samples[0]["session"],
                    "resolution": samples[0]["resolution"],
                    "validation": validations,
                    "captured_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "align_only_validated",
                    "pickup_validated": False,
                },
            )
            print(json.dumps(json.loads(MODEL.read_text()), indent=2))
        else:
            model = json.loads(MODEL.read_text())
            if model["seed"] != seed:
                raise RuntimeError("Calibration belongs to a different raised pose")
            if args.stage == "probe":
                if not np.allclose(start, origin, atol=0.3, rtol=0):
                    raise RuntimeError("Probe requires the raised reference pose")
                observation = observe()
                if (
                    observation["session"] != model["session"]
                    or observation["resolution"] != model["resolution"]
                ):
                    raise RuntimeError("Camera changed since sampling")
                target = origin.copy()
                target[0] += 5
                target[1] += 5
                same_context(target, seed)
                print(
                    "Fixed-height feedback test: +5 mm X, +5 mm Y; tool OFF", flush=True
                )
                if args.execute:
                    robot.move(target)
                return
            total = 0
            trace = []
            for iteration in range(8):
                pose = robot.check()
                same_context(pose, seed)
                obs = observe()
                if (
                    obs["session"] != model["session"]
                    or obs["resolution"] != model["resolution"]
                ):
                    raise RuntimeError("Camera context differs from calibration")
                error_mm = np.linalg.solve(
                    model["jacobian_px_per_mm"],
                    np.array(model["aim_px"]) - obs["center_px"],
                )
                print(
                    json.dumps(
                        {
                            "iteration": iteration,
                            "observation": obs,
                            "error_mm": error_mm.tolist(),
                        }
                    ),
                    flush=True,
                )
                trace.append(
                    {
                        "iteration": iteration,
                        "pose": pose,
                        "observation": obs,
                        "estimated_error_mm": error_mm.tolist(),
                        "execute": args.execute,
                    }
                )
                save(FOLDER / "alignment-latest.json", trace)
                if np.linalg.norm(error_mm) <= 0.75:
                    print(
                        "Aligned at observation height; NO descent or suction command",
                        flush=True,
                    )
                    return
                delta = correction_mm(model, obs["center_px"])
                target = pose.copy()
                target[:2] = (np.array(pose[:2]) + delta).tolist()
                same_context(target, seed)
                total += np.linalg.norm(delta)
                if total > 15:
                    raise RuntimeError("Correction travel limit reached")
                if not args.execute:
                    print("Dry run correction mm:", delta)
                    return
                robot.move(target)
            raise RuntimeError("Alignment iteration limit reached")


if __name__ == "__main__":
    main()
