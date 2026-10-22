"""End a completed, released pickup at the fixed camera observation height."""

import math


def return_to_observation(robot, height_mm, speed_mm_s, events):
    """Go straight UP only after the shared live release/health preflight.

    The caller invokes this after the pick cycle verified OFF/release outputs
    and pickup input low. robot.check() independently repeats those checks. A
    failed release, fault, unknown pose or IK discontinuity prevents this move.
    Retain pickup XY and wrist angle; this is not an arbitrary home-position move.
    """
    if not math.isfinite(height_mm) or not 200 <= height_mm <= 350:
        raise ValueError("Expected the taught observation height in robot millimeters")
    if not math.isfinite(speed_mm_s) or speed_mm_s <= 0:
        raise ValueError("Return speed must be positive and finite")
    start = robot.check()
    if height_mm < start[2] - 0.2:
        raise RuntimeError("Camera return must not descend")
    target = start.copy()
    target[2] = height_mm
    if abs(start[2] - height_mm) > 0.2:
        events.append(
            {
                "event": "return_to_observation_started",
                "target": target,
                "speed_mm_s": speed_mm_s,
            }
        )
        robot.move(target, speed=speed_mm_s)
    final = robot.check()
    if any(abs(final[i] - target[i]) > 0.3 for i in range(6)):
        raise RuntimeError("Observation return pose not verified")
    events.append({"event": "returned_to_observation", "pose": final})
    return final
