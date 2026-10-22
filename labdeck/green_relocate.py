"""Move the empty wrist to a new observation spot for operator block placement.

Default: read-only plan. With --execute, this performs only two 20 mm +X
translations at the existing observation height. The operator previously
confirmed clear tabletop space in this direction. It never descends, activates
suction, moves the block, or turns a hypothetical contact into a taught one.
"""

import argparse
from datetime import datetime, timezone
import json

import numpy as np

from .calibration_motion import CalibrationArm, value
from .green_calibrate import MODEL, SEED, FOLDER, observe, same_context, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    model = json.loads(MODEL.read_text())
    seed = json.loads(SEED.read_text())
    if model["seed"] != seed:
        raise RuntimeError("Calibration/reference mismatch")
    with CalibrationArm() as robot:
        start = robot.check()
        same_context(start, seed)
        if start[2] < 200:
            raise RuntimeError("Relocation requires high observation pose")
        observation = observe()
        if (
            observation["session"] != model["session"]
            or observation["resolution"] != model["resolution"]
        ):
            raise RuntimeError("Camera context changed")
        target = start.copy()
        target[0] += 40
        plan = robot.preview(target)
        # Check a hypothetical descent at the NEW spot, seeding each solution
        # with its predecessor. This is planning only, not obstacle clearance.
        joints = value(
            robot.arm.get_inverse_kinematics(
                target,
                input_is_radian=False,
                return_is_radian=False,
                limited=False,
                ref_angles=value(robot.arm.get_servo_angle())[:6],
            )
        )
        max_jump = 0
        min_wrist = abs(joints[4])
        floor = seed["contact_reference"][2]
        for z in np.linspace(
            target[2], floor, int(np.ceil((target[2] - floor) / 2)) + 1
        )[1:]:
            pose = target.copy()
            pose[2] = float(z)
            solution = value(
                robot.arm.get_inverse_kinematics(
                    pose,
                    input_is_radian=False,
                    return_is_radian=False,
                    limited=False,
                    ref_angles=joints[:6],
                )
            )
            jump = max(abs(x - y) for x, y in zip(solution, joints))
            if jump > 10 or value(robot.arm.is_joint_limit(solution, is_radian=False)):
                raise RuntimeError("Candidate descent still discontinuous/unreachable")
            max_jump = max(max_jump, jump)
            min_wrist = min(min_wrist, abs(solution[4]))
            joints = solution
        record = {
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "executed": args.execute,
            "plan": plan,
            "hypothetical_descent_max_joint_step_deg": max_jump,
            "hypothetical_descent_min_abs_joint5_deg": min_wrist,
            "guide_aim_px": model["aim_px"],
            "resolution": model["resolution"],
            "camera_session": model["session"],
            "original_model": model,
            "contact_teaching_required": True,
            "status": "plan_only",
        }
        print(
            json.dumps(
                {k: v for k, v in record.items() if k != "original_model"}, indent=2
            ),
            flush=True,
        )
        path = FOLDER / "relocation.json"
        if args.execute:
            # Invalidate old XY/contact context BEFORE any relocation. Retain an
            # ignored archive for the stationary camera placement guide only.
            save(FOLDER / "pre-relocation-model.json", model)
            MODEL.unlink()
            save(path, {**record, "status": "relocation_started"})
            for dx in [20, 40]:
                waypoint = start.copy()
                waypoint[0] += dx
                robot.move(waypoint)
                save(
                    path,
                    {
                        **record,
                        "status": "relocation_checkpoint",
                        "actual_pose": robot.check(),
                    },
                )
            save(
                path,
                {
                    **record,
                    "status": "awaiting_operator_block_placement",
                    "actual_pose": robot.check(),
                },
            )
            print(
                "Idle at new observation spot; operator may position block. No descent/tool command.",
                flush=True,
            )
        else:
            save(FOLDER / "relocation-plan.json", record)


if __name__ == "__main__":
    main()
