"""Read-only boundary around UFACTORY's SDK.

Students should be able to audit this file in one sitting. It exposes snapshots,
not the SDK object. No enable, mode change, movement, gripper, or reset method is
called. An SDK connection is NOT a determination that a robot is safe to move.
"""

import threading
import time
from xarm.wrapper import XArmAPI


class RobotObserver:
    def __init__(self, ip, api_factory=XArmAPI):
        self.ip = ip
        self.api_factory = api_factory
        self.lock = threading.Lock()
        self.data = {
            "connected": False,
            "error": "Waiting for first SDK read",
            "values": {},
        }
        self.updated = 0

    def snapshot(self):
        with self.lock:
            result = {**self.data, "values": dict(self.data["values"])}
            result["age_seconds"] = (
                round(time.monotonic() - self.updated, 1) if self.updated else None
            )
        result["fresh"] = bool(
            result["connected"]
            and result["age_seconds"] is not None
            and result["age_seconds"] < 8
        )
        return result

    def run(self, stop):
        arm = None
        try:
            # Disable unsolicited report/keepalive workers; our own loop performs
            # a short, explicit list of getters every three seconds.
            arm = self.api_factory(
                self.ip, do_not_open=True, enable_report=False, timed_comm=False
            )
            arm.connect()
            version_code, version = arm.get_version()
            if version_code != 0:
                raise RuntimeError(f"Version query returned {version_code}")
            while not stop.is_set():
                values = {"version": version}
                failures = []
                for key, getter in (
                    ("state", arm.get_state),
                    ("errors", arm.get_err_warn_code),
                    ("pose", arm.get_position),
                    ("joints", arm.get_servo_angle),
                ):
                    code, value = getter()
                    values[key] = value if code == 0 else None
                    if code != 0:
                        failures.append(f"{key}: SDK return {code}")
                with self.lock:
                    self.data = {
                        "connected": bool(arm.connected),
                        "error": "; ".join(failures),
                        "values": values,
                    }
                    self.updated = time.monotonic()
                stop.wait(3)
        except Exception as exc:
            with self.lock:
                self.data = {"connected": False, "error": str(exc), "values": {}}
                self.updated = time.monotonic()
        finally:
            if arm is not None:
                arm.disconnect()
