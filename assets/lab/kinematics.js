/* Lite 6 forward/inverse kinematics for the Lab simulator.
 *
 * Geometry is UFACTORY's own: joint origins from xarm_ros2
 * (xarm_description/config/kinematics/default/lite6_default_kinematics.yaml,
 * BSD-3-Clause). Every joint rotates about its local z axis. Units here:
 * millimeters and degrees at the interface, radians inside.
 *
 * Poses use the xArm convention [x, y, z, roll, pitch, yaw]: fixed-axis
 * roll about X, then pitch about Y, then yaw about Z (R = Rz·Ry·Rx), in the
 * base frame, for the tool center point (flange + TCP offset).
 *
 * The simulator never talks to the robot. tests/test_lab_kinematics.py checks
 * this FK against the controller's own get_forward_kinematics results.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Lite6 = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const D2R = Math.PI / 180;
  const R2D = 180 / Math.PI;

  // [x, y, z] mm and [roll, pitch, yaw] rad of each joint in its parent link.
  const JOINTS = [
    { xyz: [0, 0, 243.5], rpy: [0, 0, 0] },
    { xyz: [0, 0, 0], rpy: [1.5708, -1.5708, 3.1416] },
    { xyz: [200.2, 0, 0], rpy: [-3.1416, 0, 1.5708] },
    { xyz: [87, -227.61, 0], rpy: [1.5708, 0, 0] },
    { xyz: [0, 0, 0], rpy: [1.5708, 0, 0] },
    { xyz: [0, 62.5, 0], rpy: [-1.5708, 0, 0] },
  ];
  // Degrees, from the default (unlimited-turn) Lite 6 URDF macro.
  const LIMITS = [
    [-360, 360],
    [-150, 150],
    [-3.5, 300],
    [-360, 360],
    [-124, 124],
    [-360, 360],
  ];

  // ---- 4x4 matrices, row-major arrays of 16 ----
  function mul(a, b) {
    const o = new Array(16).fill(0);
    for (let r = 0; r < 4; r++)
      for (let c = 0; c < 4; c++)
        for (let k = 0; k < 4; k++) o[r * 4 + c] += a[r * 4 + k] * b[k * 4 + c];
    return o;
  }
  function rotRPY(roll, pitch, yaw) {
    const cr = Math.cos(roll), sr = Math.sin(roll);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    // Rz(yaw) · Ry(pitch) · Rx(roll)
    return [
      cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr,
      sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr,
      -sp, cp * sr, cp * cr,
    ];
  }
  function transform(xyz, rpy) {
    const r = rotRPY(rpy[0], rpy[1], rpy[2]);
    return [r[0], r[1], r[2], xyz[0], r[3], r[4], r[5], xyz[1], r[6], r[7], r[8], xyz[2], 0, 0, 0, 1];
  }
  function rotZ(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }
  let ORIGINS = JOINTS.map((j) => transform(j.xyz, j.rpy));
  let OFFSETS = [0, 0, 0, 0, 0, 0];

  /**
   * Use per-arm calibrated geometry (scripts/fit_lab_kinematics.py fits it to
   * the controller's own FK; nominal geometry is off by up to ~10 mm).
   * joints: 6 × { xyz: [mm], rpy: [rad], offset_rad }.
   */
  function setGeometry(joints) {
    if (!Array.isArray(joints) || joints.length !== 6) return false;
    ORIGINS = joints.map((j) => transform(j.xyz, j.rpy));
    OFFSETS = joints.map((j) => j.offset_rad || 0);
    return true;
  }

  function toRPY(m) {
    // Inverse of Rz·Ry·Rx; pitch in [-90, 90].
    const pitch = Math.atan2(-m[8], Math.hypot(m[0], m[4]));
    let roll, yaw;
    if (Math.abs(Math.cos(pitch)) < 1e-9) {
      roll = 0;
      yaw = Math.atan2(-m[1], m[5]);
    } else {
      roll = Math.atan2(m[9], m[10]);
      yaw = Math.atan2(m[4], m[0]);
    }
    return [roll, pitch, yaw];
  }

  /** Link frames for drawing: [base, link1..link6], each a 4x4 in mm. */
  function linkFrames(jointsDeg) {
    const frames = [];
    let t = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
    frames.push(t);
    for (let i = 0; i < 6; i++) {
      t = mul(mul(t, ORIGINS[i]), rotZ(jointsDeg[i] * D2R + OFFSETS[i]));
      frames.push(t);
    }
    return frames;
  }

  function tcpMatrix(jointsDeg, tcpOffset = [0, 0, 0, 0, 0, 0]) {
    const flange = linkFrames(jointsDeg)[6];
    const off = transform(tcpOffset.slice(0, 3), tcpOffset.slice(3).map((a) => a * D2R));
    return mul(flange, off);
  }

  /** Joint angles (deg) → TCP pose [x, y, z, roll, pitch, yaw] (mm, deg). */
  function fk(jointsDeg, tcpOffset) {
    const m = tcpMatrix(jointsDeg, tcpOffset);
    const rpy = toRPY(m).map((a) => a * R2D);
    return [m[3], m[7], m[11], ...rpy];
  }

  function poseMatrix(pose) {
    return transform(pose.slice(0, 3), pose.slice(3).map((a) => a * D2R));
  }

  // 6-vector error between two poses: position (mm) and rotation (rad, axis-angle-ish).
  function poseError(current, target) {
    const e = [target[3] - current[3], target[7] - current[7], target[11] - current[11]];
    // R_err = R_target · R_currentᵀ ; small-angle vector from its skew part.
    const R = (m) => [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]];
    const a = R(target), b = R(current);
    const re = new Array(9).fill(0);
    for (let r = 0; r < 3; r++)
      for (let c = 0; c < 3; c++)
        for (let k = 0; k < 3; k++) re[r * 3 + c] += a[r * 3 + k] * b[c * 3 + k];
    const w = [(re[7] - re[5]) / 2, (re[2] - re[6]) / 2, (re[3] - re[1]) / 2];
    return [...e, ...w];
  }

  function solve6(A, b, lambda) {
    // (AᵀA + λ²I) x = Aᵀb via Gaussian elimination.
    const n = 6;
    const M = [];
    for (let i = 0; i < n; i++) {
      const row = [];
      for (let j = 0; j < n; j++) {
        let s = i === j ? lambda * lambda : 0;
        for (let k = 0; k < 6; k++) s += A[k][i] * A[k][j];
        row.push(s);
      }
      let rhs = 0;
      for (let k = 0; k < 6; k++) rhs += A[k][i] * b[k];
      row.push(rhs);
      M.push(row);
    }
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      [M[c], M[p]] = [M[p], M[c]];
      const d = M[c][c] || 1e-12;
      for (let r = 0; r < n; r++) {
        if (r === c) continue;
        const f = M[r][c] / d;
        for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    return M.map((row, i) => row[n] / (row[i] || 1e-12));
  }

  /**
   * Numeric IK from a seed (damped least squares). Returns
   * { joints, ok, posErr, rotErrDeg }. Stays on the seed's branch, which is
   * what a linear move does on the real controller.
   */
  function ik(pose, seedDeg, tcpOffset, iterations = 60) {
    const target = poseMatrix(pose);
    let q = seedDeg.slice(0, 6);
    let err = null;
    for (let it = 0; it < iterations; it++) {
      const cur = tcpMatrix(q, tcpOffset);
      err = poseError(cur, target);
      // Rotation error weighted so 1° ≈ 2 mm.
      const w = [1, 1, 1, 115, 115, 115];
      const ew = err.map((v, i) => v * w[i]);
      if (Math.hypot(...ew.slice(0, 3)) < 0.01 && Math.hypot(...ew.slice(3)) < 0.02) break;
      const J = [[], [], [], [], [], []];
      const h = 1e-3;
      for (let j = 0; j < 6; j++) {
        const dq = q.slice();
        dq[j] += h;
        const ej = poseError(tcpMatrix(dq, tcpOffset), target);
        for (let k = 0; k < 6; k++) J[k][j] = ((err[k] - ej[k]) / h) * w[k];
      }
      const step = solve6(J, ew, 0.5);
      const maxStep = Math.max(...step.map(Math.abs));
      const scale = maxStep > 10 ? 10 / maxStep : 1;
      q = q.map((v, i) => v + step[i] * scale);
    }
    const posErr = Math.hypot(err[0], err[1], err[2]);
    const rotErrDeg = Math.hypot(err[3], err[4], err[5]) * R2D;
    return { joints: q, ok: posErr < 0.5 && rotErrDeg < 0.2, posErr, rotErrDeg };
  }

  function limitViolation(jointsDeg) {
    for (let i = 0; i < 6; i++) {
      const [lo, hi] = LIMITS[i];
      if (jointsDeg[i] < lo || jointsDeg[i] > hi) return i;
    }
    return -1;
  }

  return { JOINTS, LIMITS, setGeometry, linkFrames, fk, ik, poseMatrix, limitViolation };
});
