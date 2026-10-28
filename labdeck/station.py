"""Published calibration for the shared Lite 6 station.

The arm, camera and camera mount are the same physical station on every
computer, so its measured profiles (pickup, shelf path, hand anchor, start
poses, kinematic fit, TCP report) are tracked in station/. At launch, any of
those files missing from the ignored local/ folder is copied in. A file that
already exists in local/ is never overwritten: local/ stays the working copy
that recalibration writes to.
"""

import shutil

from .calibration_motion import ROOT

STATION = ROOT / "station"


def seed_local(station=STATION, local=ROOT / "local"):
    """Copy published station files missing from local/; return what was copied."""
    copied = []
    for source in sorted(station.rglob("*.json")):
        target = local / source.relative_to(station)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(source.relative_to(station)))
    return copied
