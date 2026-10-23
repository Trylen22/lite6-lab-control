"""Movement speed authorization shared by the supervised pickup scripts.

The operator authorized two successive 15% increases: 1.15 * 1.15 = 1.3225
relative to the original speeds. This scales speed ONLY. It does not authorize
motion, change acceleration/contact limits, or bypass live preflight/seal gates.
The command-line default remains 1.0; the next explicitly requested test will
select 1.3225. Merely importing this module never connects to hardware.
"""

import math

MAX_SPEED_SCALE = 1.3225


def validate_speed_scale(scale):
    """Reject nonfinite/out-of-range values before any tool or movement call."""
    if not math.isfinite(scale) or not 1 <= scale <= MAX_SPEED_SCALE:
        raise ValueError(
            f"Speed scale must be between 1.0 and authorized {MAX_SPEED_SCALE}"
        )
    return scale


# The subsequent explicit speed-tuning request covers empty-tool travel only.
# Contact, loaded lift/lower, and image-alignment scaling retain the old cap.
MAX_CLEAR_TRAVEL_MM_S = 60.0
CLEARANCE_ABOVE_FLOOR_MM = 15.0

# Button Pick & Place profile (2026-10-23 operator speed request: a 52 mm
# pick took 69 s). Most of that time was low ACCELERATION (2-10 mm/s^2), so
# short moves never reached their speed. Every gate is unchanged: fresh
# frames, IK previews, 0.5 mm contact steps with a 3-read seal check, seal
# feedback before lift and during the hold, release verification.
CLEAR_ACCEL_MM_S2 = 200  # Empty tool, >= 15 mm above the block.
NEAR_CONTACT_MM_S = 10  # Final 10 mm approach / first retreat, empty tool.
NEAR_CONTACT_ACCEL_MM_S2 = 50
CONTACT_STEP_MM_S = 2.5  # Each 0.5 mm search step; step size unchanged.
CONTACT_STEP_ACCEL_MM_S2 = 20
LOADED_MM_S = 10  # 10 mm lift and lower while holding the block.
LOADED_ACCEL_MM_S2 = 50
SEAL_HOLD_SECONDS = 0.5  # Monitored hold, seal read every 0.1 s.
ALIGN_GAIN = 0.9  # Fraction of the measured error moved per alignment step.
ALIGN_MAX_STEP_MM = 60


def clear_travel_speed(profile):
    """Validate a separate empty-tool rate; old profiles keep their old speed."""
    baseline = 5 * validate_speed_scale(profile["speed_scale"])
    speed = profile.get("clear_travel_mm_s", baseline)
    if (
        isinstance(speed, bool)
        or not math.isfinite(speed)
        or not baseline <= speed <= MAX_CLEAR_TRAVEL_MM_S
    ):
        raise ValueError(
            f"Clear travel must be between {baseline} and {MAX_CLEAR_TRAVEL_MM_S} mm/s"
        )
    return speed
