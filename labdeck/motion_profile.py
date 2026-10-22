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
MAX_CLEAR_TRAVEL_MM_S = 20.0
CLEARANCE_ABOVE_FLOOR_MM = 15.0


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
