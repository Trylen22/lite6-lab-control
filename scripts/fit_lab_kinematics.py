"""Fit the Lab simulator's Lite 6 geometry to THIS arm's controller.

The published URDF geometry is nominal; each controller carries factory-
calibrated kinematics, so nominal FK differs by several millimeters. This
script asks the controller for its own forward kinematics at random joint
angles (get_forward_kinematics: a computation, the arm does not move),
then fits each joint origin (xyz, rpy) and joint zero offset by
Gauss-Newton least squares. The result goes to ignored local/
lab-kinematics.json, which the dashboard serves to the simulator.

Usage: .venv/bin/python scripts/fit_lab_kinematics.py [--samples 300]
"""

import argparse
import json
from pathlib import Path
import random
import tomllib

import numpy as np
from xarm.wrapper import XArmAPI

ROOT = Path(__file__).resolve().parents[1]
NOMINAL = [
    ([0, 0, 243.5], [0, 0, 0]),
    ([0, 0, 0], [1.5708, -1.5708, 3.1416]),
    ([200.2, 0, 0], [-3.1416, 0, 1.5708]),
    ([87, -227.61, 0], [1.5708, 0, 0]),
    ([0, 0, 0], [1.5708, 0, 0]),
    ([0, 62.5, 0], [-1.5708, 0, 0]),
]
LIMITS = [(-170, 170), (-100, 100), (5, 160), (-170, 170), (-115, 115), (-170, 170)]


def rot(r, p, y):
    cr, sr, cp, sp, cy, sy = (
        np.cos(r),
        np.sin(r),
        np.cos(p),
        np.sin(p),
        np.cos(y),
        np.sin(y),
    )
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ]
    )


def fk(params, joints_deg):
    """params: 6 × [x, y, z, roll, pitch, yaw, joint_offset_rad]."""
    t = np.eye(4)
    for i in range(6):
        x, y, z, r, p, w, off = params[i]
        origin = np.eye(4)
        origin[:3, :3] = rot(r, p, w)
        origin[:3, 3] = [x, y, z]
        a = np.radians(joints_deg[i]) + off
        rz = np.eye(4)
        rz[:2, :2] = [[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]
        t = t @ origin @ rz
    return t


def residual(params, joints, targets):
    out = []
    for q, target in zip(joints, targets):
        m = fk(params, q)
        out.extend(m[:3, 3] - target[:3, 3])
        # Rotation residual scaled so 1 degree ≈ 2 mm.
        re = target[:3, :3] @ m[:3, :3].T
        w = (
            np.array([re[2, 1] - re[1, 2], re[0, 2] - re[2, 0], re[1, 0] - re[0, 1]])
            / 2
        )
        out.extend(w * 115)
    return np.array(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=300)
    args = parser.parse_args()
    cache = ROOT / "local/lab-fk-samples.json"
    if cache.exists():
        samples = json.loads(cache.read_text())
    else:
        config = tomllib.loads((ROOT / "local/lab.toml").read_text())
        arm = XArmAPI(
            config["robot"]["ip"],
            do_not_open=True,
            enable_report=False,
            timed_comm=False,
        )
        arm.connect()
        random.seed(11)
        samples = []
        try:
            for _ in range(args.samples):
                q = [round(random.uniform(lo, hi), 3) for lo, hi in LIMITS]
                code, pose = arm.get_forward_kinematics(
                    q, input_is_radian=False, return_is_radian=False
                )
                if code == 0:
                    samples.append({"joints": q, "pose": list(pose)})
        finally:
            arm.disconnect()
        cache.write_text(json.dumps(samples))
    joints, targets = [], []
    for item in samples:
        m = np.eye(4)
        m[:3, :3] = rot(*np.radians(item["pose"][3:6]))
        m[:3, 3] = item["pose"][:3]
        joints.append(item["joints"])
        targets.append(m)
    params = np.array([[*xyz, *rpy, 0.0] for xyz, rpy in NOMINAL], dtype=float)
    before = residual(params, joints, targets)
    flat = params.ravel()
    # Levenberg-Marquardt: several parameters trade off against each other,
    # so damp every step and accept it only when the fit improves.
    r = residual(flat.reshape(6, 7), joints, targets)
    cost = float(r @ r)
    lam = 1e-2
    for _ in range(60):
        jac = np.empty((r.size, flat.size))
        for k in range(flat.size):
            h = 1e-5 if k % 7 >= 3 else 1e-3
            step = flat.copy()
            step[k] += h
            jac[:, k] = (residual(step.reshape(6, 7), joints, targets) - r) / h
        jtj = jac.T @ jac
        g = jac.T @ r
        while True:
            delta = np.linalg.lstsq(
                jtj + lam * np.diag(np.diag(jtj) + 1e-9), -g, rcond=1e-10
            )[0]
            trial = flat + delta
            rt = residual(trial.reshape(6, 7), joints, targets)
            ct = float(rt @ rt)
            if ct < cost:
                flat, r, lam = trial, rt, max(lam / 3, 1e-7)
                improved = cost - ct
                cost = ct
                break
            lam *= 4
            if lam > 1e8:
                improved = 0
                break
        if improved < 1e-9 * cost or lam > 1e8:
            break
    after = residual(flat.reshape(6, 7), joints, targets).reshape(-1, 6)
    pos = np.linalg.norm(after[:, :3], axis=1)
    rotd = np.linalg.norm(after[:, 3:], axis=1) / 115 * 180 / np.pi
    b = before.reshape(-1, 6)
    report = {
        "samples": len(joints),
        "nominal_max_position_mm": float(np.max(np.linalg.norm(b[:, :3], axis=1))),
        "fitted_max_position_mm": float(pos.max()),
        "fitted_rms_position_mm": float(np.sqrt(np.mean(pos**2))),
        "fitted_max_rotation_deg": float(rotd.max()),
    }
    out = {
        "source": "Fitted to this controller's get_forward_kinematics (no motion)",
        "joints": [
            {
                "xyz": list(map(float, p[:3])),
                "rpy": list(map(float, p[3:6])),
                "offset_rad": float(p[6]),
            }
            for p in flat.reshape(6, 7)
        ],
        "fit": report,
    }
    (ROOT / "local/lab-kinematics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
