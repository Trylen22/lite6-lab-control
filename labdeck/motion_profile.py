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
