/* Lab interpreter: a UFACTORY Studio block program → a simulated timeline.
 *
 * Input is a plain tree (see treeFromDom in lab.js):
 *   { type, id, fields: {name: text}, values: {name: tree}, statements:
 *     {name: tree}, next: tree, data }
 * Block types and field meanings follow UFACTORY's own Studio converter
 * (xarm/tools/blockly in the xArm Python SDK, BSD). Fields are read the way
 * that converter reads them, so projects exported from Studio run here.
 *
 * Output is a list of segments the 3D view plays back, plus findings that
 * point at the block that caused them. Nothing here talks to the robot.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("./kinematics.js"));
  else root.LabProgram = factory(root.Lite6);
})(typeof self !== "undefined" ? self : this, function (K) {
  "use strict";

  const DEFAULTS = {
    angleSpeed: 20, // deg/s (Studio "set joint speed")
    angleAcc: 500, // deg/s²
    tcpSpeed: 100, // mm/s (Studio "set speed")
    tcpAcc: 2000, // mm/s²
  };
  const LINEAR_STEP_MM = 5;
  const MAX_SEGMENTS = 4000;
  const MAX_STEPS = 20000;
  const WRIST_JUMP_DEG = 10;
  // UFACTORY's "reset" (move_gohome) returns every joint to zero.
  const HOME = [0, 0, 0, 0, 0, 0];

  class ProgramError extends Error {
    constructor(message, blockId) {
      super(message);
      this.blockId = blockId;
    }
  }

  // Trapezoidal profile: time to travel `distance` at `speed`, `acc`.
  function travelTime(distance, speed, acc) {
    if (distance <= 0) return 0;
    const ramp = speed / acc;
    const rampDist = speed * ramp;
    return distance >= rampDist ? ramp + distance / speed : 2 * Math.sqrt(distance / acc);
  }
  function profile(t, total, distance, speed, acc) {
    // Fraction of the path covered at time t (0..1), same profile as travelTime.
    if (total <= 0) return 1;
    const ramp = Math.min(speed / acc, total / 2);
    const vmax = acc * ramp;
    let s;
    if (t < ramp) s = 0.5 * acc * t * t;
    else if (t < total - ramp) s = 0.5 * acc * ramp * ramp + vmax * (t - ramp);
    else {
      const td = total - t;
      s = distance - 0.5 * acc * td * td;
    }
    return Math.max(0, Math.min(1, s / distance));
  }

  function num(text, blockId, what) {
    const v = Number(text);
    if (!Number.isFinite(v)) throw new ProgramError(`${what} is not a number`, blockId);
    return v;
  }

  function compile(tree, options = {}) {
    const tcp = options.tcpOffset || [0, 0, 0, 0, 0, 0];
    const env = {
      ...DEFAULTS,
      joints: (options.startJoints || HOME).slice(0, 6),
      suction: false,
      vars: Object.create(null),
      procs: Object.create(null),
    };
    const segments = [];
    const findings = [];
    let steps = 0;

    const warn = (blockId, message, level = "warning") => {
      if (!findings.some((f) => f.blockId === blockId && f.message === message))
        findings.push({ blockId, message, level });
    };

    function guard(blockId) {
      if (++steps > MAX_STEPS) throw new ProgramError("Program ran too long (loop that never ends?)", blockId);
      if (segments.length > MAX_SEGMENTS) throw new ProgramError("Too many moves to simulate", blockId);
    }

    function checkJoints(q, blockId) {
      const bad = K.limitViolation(q);
      if (bad >= 0) warn(blockId, `J${bad + 1} goes past its limit (${q[bad].toFixed(1)}°)`, "error");
      const floorZ = options.tableZ ?? -Infinity;
      const frames = K.linkFrames(q);
      for (let i = 3; i <= 6; i++) {
        if (frames[i][11] < floorZ - 1) {
          warn(blockId, "Part of the arm goes below the table", "error");
          break;
        }
      }
      const tool = K.fk(q, tcp);
      if (tool[2] < floorZ) warn(blockId, `Tool goes below the table (z ${tool[2].toFixed(0)} mm)`, "error");
      const box = options.obstacle;
      if (box && tool[0] > box.min[0] && tool[0] < box.max[0] && tool[1] > box.min[1] && tool[1] < box.max[1] && tool[2] > box.min[2] && tool[2] < box.max[2])
        warn(blockId, `Tool enters the ${box.name}`, "error");
    }

    function jointMove(target, blockId) {
      const start = env.joints.slice();
      const delta = Math.max(...target.map((v, i) => Math.abs(v - start[i])));
      const duration = travelTime(delta, env.angleSpeed, env.angleAcc);
      const samples = [];
      const n = Math.max(2, Math.ceil(delta / 2));
      for (let k = 0; k <= n; k++) {
        const f = k / n;
        const q = start.map((v, i) => v + (target[i] - v) * f);
        samples.push(q);
        if (k % 4 === 0 || k === n) checkJoints(q, blockId);
      }
      if (Math.max(Math.abs(target[3] - start[3]), Math.abs(target[5] - start[5])) > 150)
        warn(blockId, "The wrist spins more than 150° here; check the cable", "warning");
      segments.push({ kind: "joint", blockId, duration, samples, distance: delta, speed: env.angleSpeed, acc: env.angleAcc, suction: env.suction });
      env.joints = target.slice();
    }

    function linearMove(targetPose, blockId) {
      const startPose = K.fk(env.joints, tcp);
      const dist = Math.hypot(targetPose[0] - startPose[0], targetPose[1] - startPose[1], targetPose[2] - startPose[2]);
      const n = Math.max(1, Math.ceil(dist / LINEAR_STEP_MM));
      const samples = [env.joints.slice()];
      let q = env.joints.slice();
      // Orientation: interpolate roll/pitch/yaw by the shortest way round.
      const ang = (a, b) => ((((b - a) % 360) + 540) % 360) - 180;
      for (let k = 1; k <= n; k++) {
        const f = k / n;
        const pose = startPose.map((v, i) => (i < 3 ? v + (targetPose[i] - v) * f : v + ang(v, targetPose[i]) * f));
        const sol = K.ik(pose, q, tcp);
        if (!sol.ok) {
          warn(blockId, `Unreachable: the arm can't get to ${pose.slice(0, 3).map((v) => v.toFixed(0)).join(", ")} mm`, "error");
          break;
        }
        const jump = Math.max(...sol.joints.map((v, i) => Math.abs(v - q[i])));
        if (jump > WRIST_JUMP_DEG) warn(blockId, `The arm flips its joints mid-line (${jump.toFixed(0)}° jump)`, "error");
        q = sol.joints;
        samples.push(q);
        if (k % 4 === 0 || k === n) checkJoints(q, blockId);
      }
      const duration = travelTime(dist, env.tcpSpeed, env.tcpAcc);
      segments.push({ kind: "linear", blockId, duration, samples, distance: dist, speed: env.tcpSpeed, acc: env.tcpAcc, suction: env.suction });
      env.joints = q.slice();
    }

    function value(node, blockId) {
      if (!node) throw new ProgramError("A slot is empty", blockId);
      const f = node.fields || {};
      switch (node.type) {
        case "math_number":
          return num(f.NUM, node.id, "Number");
        case "logic_boolean":
          return f.BOOL === "TRUE";
        case "variables_get":
          return env.vars[f.VAR] ?? 0;
        case "math_arithmetic": {
          const a = value(node.values?.A, node.id), b = value(node.values?.B, node.id);
          return { ADD: a + b, MINUS: a - b, MULTIPLY: a * b, DIVIDE: a / b, POWER: a ** b }[f.OP];
        }
        case "logic_compare": {
          const a = value(node.values?.A, node.id), b = value(node.values?.B, node.id);
          return { EQ: a === b, NEQ: a !== b, LT: a < b, LTE: a <= b, GT: a > b, GTE: a >= b }[f.OP];
        }
        case "logic_operation": {
          const a = value(node.values?.A, node.id), b = value(node.values?.B, node.id);
          return f.OP === "AND" ? a && b : a || b;
        }
        case "logic_negate":
          return !value(node.values?.BOOL, node.id);
        default:
          throw new ProgramError(`"${node.type}" can't be used as a value in the simulator`, node.id);
      }
    }

    function run(node) {
      while (node) {
        guard(node.id);
        exec(node);
        node = node.next;
      }
    }

    function exec(node) {
      const f = node.fields || {};
      const id = node.id;
      const fieldList = node.fieldOrder || Object.keys(f);
      switch (node.type) {
        case "move_joints": {
          // i..n = J1..J6 (degrees), then r (blend radius), then wait.
          const names = ["i", "j", "k", "l", "m", "n"];
          const target = names.map((k, i) => num(f[k] ?? f[fieldList[i]], id, `J${i + 1}`));
          jointMove(target, id);
          break;
        }
        case "move_cartesian": {
          const target = fieldList.slice(0, 6).map((k, i) => num(f[k], id, ["X", "Y", "Z", "roll", "pitch", "yaw"][i]));
          linearMove(target, id);
          break;
        }
        case "move": {
          // Relative straight move in the base frame, like Studio's "move".
          const dir = f[fieldList[0]];
          const dist = num(f[fieldList[1]], id, "Distance");
          const axis = { forward: [0, 1], backward: [0, -1], left: [1, 1], right: [1, -1], up: [2, 1], down: [2, -1] }[dir];
          if (!axis) throw new ProgramError(`Unknown direction "${dir}"`, id);
          const pose = K.fk(env.joints, tcp);
          pose[axis[0]] += axis[1] * dist;
          linearMove(pose, id);
          break;
        }
        case "reset":
          jointMove(HOME, id);
          break;
        case "set_speed":
          env.tcpSpeed = Math.max(0.1, num(f[fieldList[0]], id, "Speed"));
          break;
        case "set_acceleration":
          env.tcpAcc = Math.max(1, num(f[fieldList[0]], id, "Acceleration"));
          break;
        case "set_angle_speed":
          env.angleSpeed = Math.max(0.1, num(f[fieldList[0]], id, "Joint speed"));
          break;
        case "set_angle_acceleration":
          env.angleAcc = Math.max(1, num(f[fieldList[0]], id, "Joint acceleration"));
          break;
        case "wait": {
          const sec = value(node.values?.sec, id);
          segments.push({ kind: "wait", blockId: id, duration: Math.max(0, sec), samples: [env.joints.slice()], suction: env.suction });
          break;
        }
        case "set_suction_cup": {
          env.suction = (f.trigger ?? f[fieldList[0]]) === "ON";
          segments.push({ kind: "suction", blockId: id, duration: 0.3, samples: [env.joints.slice()], suction: env.suction });
          break;
        }
        case "controls_repeat_ext": {
          const times = Math.floor(value(node.values?.TIMES, id));
          for (let i = 0; i < times; i++) run(node.statements?.DO);
          break;
        }
        case "controls_whileUntil": {
          const until = f.MODE === "UNTIL";
          while (until ? !value(node.values?.BOOL, id) : value(node.values?.BOOL, id)) {
            guard(id);
            run(node.statements?.DO);
          }
          break;
        }
        case "controls_if": {
          let i = 0;
          let done = false;
          while (node.values?.["IF" + i] && !done) {
            if (value(node.values["IF" + i], id)) {
              run(node.statements?.["DO" + i]);
              done = true;
            }
            i++;
          }
          if (!done && node.statements?.ELSE) run(node.statements.ELSE);
          break;
        }
        case "variables_set":
          env.vars[f.VAR] = value(node.values?.VALUE, id);
          break;
        case "math_change":
          env.vars[f.VAR] = (env.vars[f.VAR] ?? 0) + value(node.values?.DELTA, id);
          break;
        case "procedures_defnoreturn":
          break;
        case "procedures_callnoreturn": {
          const body = env.procs[node.mutationName];
          if (!body) throw new ProgramError(`No function named "${node.mutationName}"`, id);
          run(body);
          break;
        }
        case "loop_run_forever":
          warn(id, "Runs forever on the arm; the simulator plays it 3 times", "warning");
          for (let i = 0; i < 3; i++) run(node.statements?.DO);
          break;
        default:
          warn(id, `"${node.studioType || node.type}" isn't simulated; skipped`, "info");
      }
    }

    // Top-level stacks: function definitions first, then everything else in order.
    const stacks = Array.isArray(tree) ? tree : [tree];
    for (const stack of stacks)
      if (stack?.type === "procedures_defnoreturn") env.procs[stack.fields?.NAME] = stack.statements?.STACK;
    try {
      for (const stack of stacks) if (stack && stack.type !== "procedures_defnoreturn") run(stack);
    } catch (error) {
      if (!(error instanceof ProgramError)) throw error;
      findings.push({ blockId: error.blockId, message: error.message, level: "error" });
    }
    let t = 0;
    for (const s of segments) {
      s.start = t;
      t += s.duration;
    }
    return { segments, findings, duration: t, endJoints: env.joints };
  }

  /** Joint angles at time t within one segment. */
  function sample(segment, t) {
    const n = segment.samples.length - 1;
    if (n <= 0 || segment.duration <= 0) return segment.samples[n];
    let f;
    if (segment.kind === "joint" || segment.kind === "linear")
      f = profile(t, segment.duration, segment.distance, segment.speed, segment.acc);
    else f = 1;
    const x = f * n;
    const i = Math.min(n - 1, Math.floor(x));
    const u = x - i;
    return segment.samples[i].map((v, k) => v + (segment.samples[i + 1][k] - v) * u);
  }

  return { compile, sample, DEFAULTS, HOME };
});
