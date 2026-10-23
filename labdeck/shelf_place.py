"""Carry a sealed block up and over to the shelf, release it, and come back.

Path taught by the operator hand-guiding the arm (scripts/record_path.py,
2026-10-23), re-expressed on the pickup wrist branch so the wrist never spins:

  lift   straight up (Cartesian) from the seal to camera height
  A      rise into the "top" arm shape with the BASE LOCKED: nothing turns
         toward the shelf until the arm is at height
  B      BASE ONLY: a level arc toward the shelf at the top height
  C      short reach out over the shelf and tilt the head (the drop pose)
  drop   release suction, verify release I/O, let the block fall
  back   C reversed, B reversed (turn back at height), then down to the
         pickup start so the next cycle can begin

Every joint segment is a single mode-0 joint move. Before sending it, the
straight joint path is sampled with forward kinematics: no joint limits, and
the tool tip stays above a per-segment floor (A >= camera height, B and C
>= top height - 5 mm). While the block is held, attachment feedback is read
after every move; a lost seal stops with no recovery move. Joint checks are
not obstacle detection: the taught path is what clears the shelf.
"""

import json
import time

import numpy as np

from .calibration_motion import ROOT
from scripts.taught_pick_trial import read_value, require_zero
from .suction import checked_vacuum

SHELF = ROOT / "local/shelf-place.json"
LOADED_JOINT_DEG_S = 30
LOADED_JOINT_ACCEL = 80
EMPTY_JOINT_DEG_S = 40
EMPTY_JOINT_ACCEL = 120
LOADED_LIFT_MM_S = 40
LOADED_LIFT_ACCEL = 100
ARRIVED_DEG = 0.3


def load_shelf(path=SHELF):
    data = json.loads(path.read_text())
    top = np.array(data["top_joints_deg"], dtype=float)
    drop = np.array(data["drop_joints_deg"], dtype=float)
    if top.shape != (6,) or drop.shape != (6,) or not np.isfinite([top, drop]).all():
        raise ValueError("Invalid shelf waypoints")
    return data


class ShelfCarrier:
    def __init__(self, arm, events, progress=lambda *_: None, sleep=time.sleep):
        self.arm = arm
        self.events = events
        self.progress = progress
        self.sleep = sleep
        self.holding = True

    def healthy(self):
        errors = read_value(self.arm.get_err_warn_code(), "read errors")
        state = read_value(self.arm.get_state(), "read state")
        if errors != [0, 0] or state not in (0, 1, 2):
            raise RuntimeError(
                f"Controller not healthy: state={state}, errors={errors}"
            )

    def seal(self):
        if (
            read_value(self.arm.get_vacuum_gripper(), "vacuum feedback") != 1
            or read_value(self.arm.get_tool_digital_input(), "pickup input")[0] != 1
        ):
            raise RuntimeError(
                "Block attachment lost during carry; operator recovery required"
            )

    def joints(self):
        return np.array(read_value(self.arm.get_servo_angle(), "read joints")[:6])

    def fk(self, joints):
        return read_value(
            self.arm.get_forward_kinematics(
                [float(x) for x in joints],
                input_is_radian=False,
                return_is_radian=False,
            ),
            "forward kinematics",
        )

    def joint_move(self, target, name, floor_mm):
        target = np.array(target, dtype=float)
        self.healthy()
        start = self.joints()
        for fraction in np.linspace(0, 1, 41):
            sample = start + fraction * (target - start)
            if read_value(
                self.arm.is_joint_limit([float(x) for x in sample], is_radian=False),
                "joint limit check",
            ):
                raise RuntimeError(f"{name}: joint limit on path; no move")
            if self.fk(sample)[2] < floor_mm:
                raise RuntimeError(f"{name}: path dips below {floor_mm:.0f} mm")
        speed, accel = (
            (LOADED_JOINT_DEG_S, LOADED_JOINT_ACCEL)
            if self.holding
            else (EMPTY_JOINT_DEG_S, EMPTY_JOINT_ACCEL)
        )
        travel = float(np.max(np.abs(target - start)))
        self.events.append({"event": name, "target_joints": target.tolist()})
        require_zero(
            self.arm.set_servo_angle(
                angle=[float(x) for x in target],
                speed=speed,
                mvacc=accel,
                is_radian=False,
                wait=True,
                timeout=travel / speed + 10,
            ),
            name,
        )
        if not np.allclose(self.joints(), target, atol=ARRIVED_DEG, rtol=0):
            raise RuntimeError(f"{name}: target not reached")
        self.healthy()
        if self.holding:
            self.seal()

    def lift_to(self, z_mm):
        self.healthy()
        pose = read_value(self.arm.get_position(), "read pose")
        target = list(pose)
        target[2] = z_mm
        self.events.append({"event": "lift_to_camera_height", "target": target})
        require_zero(
            self.arm.set_position(
                *target,
                speed=LOADED_LIFT_MM_S,
                mvacc=LOADED_LIFT_ACCEL,
                is_radian=False,
                wait=True,
                timeout=abs(z_mm - pose[2]) / LOADED_LIFT_MM_S + 10,
            ),
            "lift to camera height",
        )
        reached = read_value(self.arm.get_position(), "read pose")
        if abs(reached[2] - z_mm) > 0.5:
            raise RuntimeError("Camera-height lift not reached")
        self.healthy()
        self.seal()

    def release(self):
        require_zero(
            checked_vacuum(self.arm, False, wait=False, sync=False, sleep=self.sleep),
            "release suction",
        )
        for _ in range(20):
            self.sleep(0.1)
            outputs = read_value(self.arm.get_tgpio_output_digital(), "release outputs")
            inputs = read_value(self.arm.get_tool_digital_input(), "release input")
            if outputs == [0, 1, 0, 0, 0] and inputs[0] == 0:
                self.holding = False
                self.events.append({"event": "shelf_release_verified"})
                self.sleep(0.3)  # Let the block fall clear before moving.
                return
        raise RuntimeError("Release not verified at the shelf; operator recovery")

    def run(self, shelf, camera_height_mm, pickup_start_joints):
        top = np.array(shelf["top_joints_deg"], dtype=float)
        drop = np.array(shelf["drop_joints_deg"], dtype=float)
        home = np.array(pickup_start_joints, dtype=float)
        top_z = self.fk(top)[2]
        # Prove the seal with a short lift and a monitored hold before the
        # long lift, so a weak seal drops the block ~10 mm, not ~170 mm.
        self.progress("carrying", "Lifting 10 mm and checking the seal")
        contact_z = read_value(self.arm.get_position(), "read pose")[2]
        self.lift_to(contact_z + 10)
        for _ in range(5):
            self.sleep(0.1)
            self.healthy()
            self.seal()
        self.progress("carrying", "Lifting to camera height")
        self.lift_to(camera_height_mm)
        base = self.joints()[0]
        self.progress("carrying", "Rising with the base locked")
        self.joint_move(np.r_[base, top[1:]], "shelf_rise", camera_height_mm - 1)
        self.progress("carrying", "Swinging to the shelf at height")
        self.joint_move(np.r_[drop[0], top[1:]], "shelf_turn", top_z - 5)
        self.progress("carrying", "Reaching over the shelf")
        self.joint_move(drop, "shelf_reach", top_z - 5)
        self.progress("releasing", "Releasing onto the shelf")
        self.release()
        self.progress("returning", "Backing off the shelf")
        self.joint_move(np.r_[drop[0], top[1:]], "shelf_back_off", top_z - 5)
        self.progress("returning", "Swinging back at height")
        self.joint_move(np.r_[home[0], top[1:]], "shelf_turn_back", top_z - 5)
        self.progress("returning", "Lowering to the pickup start")
        self.joint_move(home, "shelf_return_to_start", camera_height_mm - 1)
        return self.fk(home)
