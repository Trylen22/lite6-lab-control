/* How the Lite 6 sees and moves: an explainer film for the lab.
 *
 * Contract (same as Hunt_Project/animationns/html): every frame is a PURE
 * FUNCTION OF TIME. window.render(t) draws the frame at t seconds,
 * window.TOTAL is the length, window.SCENES lists {name, start, dur}.
 * ?auto=1 hides the player (scripts/render_explainer.py uses it).
 *
 * 3D: three.js with UFACTORY's Lite 6, vacuum gripper (xarm_ros2, BSD-3) and
 * the OAK-D Pro PoE on its ring stand, posed by the Lab's kinematics
 * (assets/lab/kinematics.js, calibrated to this arm when the deck serves it).
 * 2D: an overlay canvas for captions, code, the camera-image panel and plots.
 *
 * The numbers are this arm's, from its calibration and trial logs
 * (2026-10-22/23, see docs/SESSION_LOG.md). Nothing here talks to the robot.
 */
import * as THREE from "three";
import { STLLoader } from "/assets/vendor/three-addons/STLLoader.js";

const K = window.Lite6;
const W = 1920;
const H = 1080;
const QS = new URLSearchParams(location.search);
const AUTO = QS.has("auto");
const UI = '"Avenir Next", "Avenir", "Nunito Sans", system-ui, sans-serif';
const MONO = '"JetBrains Mono", "DejaVu Sans Mono", monospace';

// ---------------------------------------------------------------- data
const ORIENT = [-179.4, -2.05, 2.48]; // cup straight down (roll ≈ 180°)
const D = {
  pickupJoints: [3.4608, 20.2952, 64.3938, -179.4848, -42.2405, 180.8353],
  cameraHeight: 265.7, // flange z at the camera pose (mm)
  tip: 61, // cup tip past the flange (UFACTORY lite vacuum gripper)
  watch: [229.3, 74.3], // first calibration's watch pose XY
  // Real samples from the first calibration: offset (mm) → dot pixel (native).
  samples: [
    [[0, 0], [330.2, 58.7]],
    [[10, 0], [333.0, 39.3]],
    [[10, 10], [312.4, 36.9]],
    [[0, 10], [311.7, 56.6]],
    [[-10, 10], [310.0, 76.4]],
    [[-10, 0], [329.4, 79.1]],
    [[-10, -10], [348.8, 80.1]],
    [[0, -10], [350.8, 61.0]],
    [[10, -10], [352.3, 41.6]],
    [[0, 0], [330.6, 58.4]],
  ],
  firstFit: { aim: [330.92, 58.82], J: [[0.158, -1.963], [-1.963, -0.213]], residual: 0.73, condition: 1.03 },
  profile: { aim: [331.4, 58.3], J: [[0.097, -1.693], [-1.853, -0.123]], residual: 0.67, condition: 1.1, holdout: 2.0 },
  // A real pick from 2026-10-23: tool XY, dot pixel, remaining error (mm).
  align: [
    { xy: [290.0, 20.0], px: [266.0, 237.5], err: [98.9, -33.0] },
    { xy: [346.9, 1.0], px: [311.8, 130.1], err: [39.3, -9.3] },
    { xy: [382.3, -7.4], px: [334.0, 59.6], err: [0.6, 1.6] },
    { xy: [382.9, -6.0], px: [332.3, 58.1], err: [-0.1, 0.5] },
  ],
  contactSteps: [99.4, 98.9, 98.4, 97.9, 97.4, 96.9, 96.4, 95.9], // sealed at the last
  kinFit: { nominal: 10.3, fitted: 0.38, samples: 300 },
};

// ---------------------------------------------------------------- palette
const C = {
  blue: "#003087",
  blueHi: "#2b5fbf",
  sky: "#69b3e7",
  red: "#cb333b",
  gold: "#fbae40",
  green: "#36c25a",
  white: "#f2f5fa",
  ink2: "#c9d3e6",
  muted: "#8fa0bf",
  panel: "rgba(4, 12, 30, 0.86)",
  axisX: "#e0484f",
  axisY: "#3fbf6b",
  axisZ: "#4f8fd0",
};

// ---------------------------------------------------------------- math
const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
const lerp = (a, b, u) => a + (b - a) * u;
const ease = (u) => {
  u = clamp(u);
  return u * u * (3 - 2 * u);
};
const seg = (lt, a, b) => clamp((lt - a) / (b - a));
const win = (lt, a, b, f = 0.4) => Math.min(seg(lt, a, a + f), 1 - seg(lt, b - f, b));
const lerpArr = (a, b, u) => a.map((v, i) => v + (b[i] - v) * u);
const toUpright = ([u, v]) => [639 - u, 399 - v];

function keyed(lt, keys, mix) {
  if (lt <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++)
    if (lt <= keys[i][0]) {
      const [t0, a] = keys[i - 1], [t1, b] = keys[i];
      return mix(a, b, ease((lt - t0) / (t1 - t0)));
    }
  return keys.at(-1)[1];
}
const jointKeys = (lt, keys) => keyed(lt, keys, lerpArr);
const camKeys = (lt, keys) =>
  keyed(lt, keys, (a, b, u) => ({ a: lerp(a.a, b.a, u), e: lerp(a.e, b.e, u), d: lerp(a.d, b.d, u), T: lerpArr(a.T, b.T, u), sx: lerp(a.sx || 0, b.sx || 0, u) }));

function ik(xyz, seed, orient = ORIENT) {
  return K.ik([...xyz, ...orient], seed).joints;
}
// Trapezoid profile: fraction of a move done at time t.
function trapezoid(t, dist, v, a) {
  const ramp = Math.min(v / a, Math.sqrt(dist / a));
  const vmax = a * ramp;
  const total = 2 * ramp + Math.max(0, (dist - a * ramp * ramp) / vmax);
  t = clamp(t, 0, total);
  let s;
  if (t < ramp) s = 0.5 * a * t * t;
  else if (t < total - ramp) s = 0.5 * a * ramp * ramp + vmax * (t - ramp);
  else s = dist - 0.5 * a * (total - t) ** 2;
  const speed = t < ramp ? a * t : t < total - ramp ? vmax : a * (total - t);
  return { s: s / dist, speed, total, vmax };
}

// ---------------------------------------------------------------- 3D
const stage = document.getElementById("stage");
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.setClearColor(0x000000, 1);
stage.append(renderer.domElement);
const overlay = document.createElement("canvas");
overlay.width = W;
overlay.height = H;
stage.append(overlay);
const g = overlay.getContext("2d");

const scene3 = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, W / H, 5, 30000);
camera.up.set(0, 0, 1);
scene3.add(new THREE.HemisphereLight(0xdde6ff, 0x0a1430, 1.15));
const key = new THREE.DirectionalLight(0xffffff, 1.7);
key.position.set(900, -700, 1600);
scene3.add(key);
const rim = new THREE.DirectionalLight(0x69b3e7, 0.8);
rim.position.set(-900, 900, 500);
scene3.add(rim);

const floor = new THREE.Mesh(new THREE.CircleGeometry(1400, 64), new THREE.MeshStandardMaterial({ color: 0x0a1222, roughness: 0.95 }));
scene3.add(floor);
const grid = new THREE.GridHelper(2400, 48, 0x1b2c52, 0x13203d);
grid.rotation.x = Math.PI / 2;
grid.position.z = 0.3;
scene3.add(grid);

const loader = new STLLoader();
const geoms = {};
async function loadGeoms() {
  const names = ["link_base", "link1", "link2", "link3", "link4", "link5", "link6", "vacuum_gripper_lite"];
  await Promise.all(
    names.map(async (n) => {
      const geo = await loader.loadAsync(`/assets/lite6/${n}.stl`);
      geo.computeVertexNormals();
      geoms[n] = geo;
    }),
  );
}

const CAMERA_MOUNT = {
  offset: [75, 29.5, 18.3],
  right: [-0.0035, 0.9955, 0.095],
  up: [1.0, 0.003, 0.0055],
  back: [0.0052, 0.095, -0.9955],
};

function makeRobot(opts = {}) {
  const white = new THREE.MeshStandardMaterial({ color: 0xf2f4f7, roughness: 0.42, metalness: 0.05, transparent: !!opts.ghost, opacity: opts.ghost ?? 1, depthWrite: !opts.ghost });
  const grey = new THREE.MeshStandardMaterial({ color: 0x9aa3ad, roughness: 0.5, transparent: !!opts.ghost, opacity: opts.ghost ?? 1, depthWrite: !opts.ghost });
  if (opts.tint) white.color.set(opts.tint), grey.color.set(opts.tint);
  const names = ["link_base", "link1", "link2", "link3", "link4", "link5", "link6"];
  const links = names.map((n, i) => {
    const grp = new THREE.Group();
    grp.matrixAutoUpdate = false;
    // Own material per link so one link can be highlighted on its own.
    const mesh = new THREE.Mesh(geoms[n], (i === 0 ? grey : white).clone());
    mesh.scale.setScalar(1000);
    grp.add(mesh);
    scene3.add(grp);
    return grp;
  });
  const gripper = new THREE.Mesh(geoms.vacuum_gripper_lite, new THREE.MeshStandardMaterial({ color: opts.tint || 0x3a4150, roughness: 0.6, transparent: !!opts.ghost, opacity: opts.ghost ?? 1 }));
  gripper.scale.setScalar(1000);
  links[6].add(gripper);
  const cupTip = new THREE.Mesh(new THREE.CylinderGeometry(9, 9, 2, 24), new THREE.MeshStandardMaterial({ color: 0x1d2433 }));
  cupTip.rotation.x = Math.PI / 2;
  cupTip.position.z = D.tip - 1;
  links[6].add(cupTip);
  let camGroup = null;
  if (!opts.ghost) {
    camGroup = new THREE.Group();
    camGroup.position.set(...CAMERA_MOUNT.offset);
    camGroup.quaternion.setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(new THREE.Vector3(...CAMERA_MOUNT.right), new THREE.Vector3(...CAMERA_MOUNT.up), new THREE.Vector3(...CAMERA_MOUNT.back)),
    );
    const body = new THREE.Mesh(new THREE.BoxGeometry(111, 40, 31.3), new THREE.MeshStandardMaterial({ color: 0x23272f, roughness: 0.5 }));
    body.position.z = 15.65;
    const lens = new THREE.Mesh(new THREE.CircleGeometry(5, 20), new THREE.MeshStandardMaterial({ color: 0x0d4fbf, emissive: 0x0a2a66 }));
    lens.rotation.y = Math.PI;
    lens.position.z = -0.2;
    camGroup.add(body, lens);
    const standMat = new THREE.MeshStandardMaterial({ color: 0x6b7280, roughness: 0.6 });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(40, 3.5, 10, 40), standMat);
    ring.position.z = 4;
    const arm = new THREE.Mesh(new THREE.BoxGeometry(CAMERA_MOUNT.offset[0] - 38, 16, 8), standMat);
    arm.position.set((CAMERA_MOUNT.offset[0] + 38) / 2 - 6, CAMERA_MOUNT.offset[1] * 0.6, CAMERA_MOUNT.offset[2] / 2 + 4);
    links[6].add(camGroup, ring, arm);
  }
  return {
    links,
    cupTip,
    camGroup,
    set(q) {
      K.linkFrames(q).forEach((m, i) => {
        links[i].matrix.set(...m);
        links[i].matrixWorldNeedsUpdate = true;
      });
    },
    visible(v) {
      for (const l of links) l.visible = v;
    },
  };
}

function arrow(color, len = 90) {
  const grp = new THREE.Group();
  const mat = new THREE.MeshBasicMaterial({ color });
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.2, len, 10), mat);
  shaft.position.y = len / 2;
  const head = new THREE.Mesh(new THREE.ConeGeometry(7, 20, 16), mat);
  head.position.y = len + 10;
  grp.add(shaft, head);
  return grp;
}
function axes(len = 90) {
  const grp = new THREE.Group();
  const x = arrow(C.axisX, len);
  x.rotation.z = -Math.PI / 2;
  const y = arrow(C.axisY, len);
  const z = arrow(C.axisZ, len);
  z.rotation.x = Math.PI / 2;
  grp.add(x, y, z);
  return grp;
}

// Paths are tubes: WebGL draws lines only 1 px wide, too thin for a film.
function line(color, radius = 3.5) {
  const m = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.45, roughness: 0.5 }));
  m.userData.radius = radius;
  m.userData.key = "";
  scene3.add(m);
  return m;
}
function setLine(m, pts) {
  const key = pts.length + ":" + pts[0] + ":" + pts.at(-1);
  if (key === m.userData.key) return; // unchanged: keep the tube
  m.userData.key = key;
  m.geometry.dispose();
  if (pts.length < 2 || Math.hypot(...pts[0].map((v, i) => v - pts.at(-1)[i])) < 0.5) {
    m.geometry = new THREE.BufferGeometry();
    return;
  }
  const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p)));
  m.geometry = new THREE.TubeGeometry(curve, Math.max(8, pts.length * 3), m.userData.radius, 10, false);
}

let robot, ghostA, ghostB, baseAxes, flangeAxes, block, frustum, pathA, pathB, zone;

function build3D() {
  robot = makeRobot();
  ghostA = makeRobot({ ghost: 0.28, tint: 0x69b3e7 });
  ghostB = makeRobot({ ghost: 0.28, tint: 0xfbae40 });
  baseAxes = axes(260);
  scene3.add(baseAxes);
  flangeAxes = axes(70);
  flangeAxes.matrixAutoUpdate = false;
  scene3.add(flangeAxes);
  block = new THREE.Group();
  const cube = new THREE.Mesh(new THREE.BoxGeometry(33.35, 33.35, 33.35), new THREE.MeshStandardMaterial({ color: 0xc8a06a, roughness: 0.8 }));
  cube.position.z = 16.7;
  const dot = new THREE.Mesh(new THREE.CircleGeometry(7, 24), new THREE.MeshStandardMaterial({ color: 0x2fbf4f, emissive: 0x0c4a1c }));
  dot.position.z = 33.6;
  block.add(cube, dot);
  scene3.add(block);
  frustum = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x69b3e7, transparent: true, opacity: 0.7 }));
  scene3.add(frustum);
  pathA = line(0x69b3e7);
  pathB = line(0xfbae40);
  zone = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints([[250, -170], [390, -170], [390, 180], [250, 180]].map(([x, y]) => new THREE.Vector3(x, y, 0.8))),
    new THREE.LineDashedMaterial({ color: 0x2b5fbf, dashSize: 12, gapSize: 9 }),
  );
  zone.computeLineDistances();
  scene3.add(zone);
}

const eye = new THREE.PerspectiveCamera(55, Math.tan((40 * Math.PI) / 180) / Math.tan((27.5 * Math.PI) / 180), 10, 3000);
function updateFrustum(show) {
  frustum.visible = show;
  if (!show) return;
  robot.camGroup.add(eye);
  eye.updateMatrixWorld(true);
  const o = new THREE.Vector3().setFromMatrixPosition(eye.matrixWorld);
  const pts = [], hit = [];
  for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
    const d = new THREE.Vector3(sx, sy, 0.5).unproject(eye).sub(o).normalize();
    const p = o.clone().addScaledVector(d, d.z < -1e-3 ? (33.35 - o.z) / d.z : 300);
    hit.push(p);
    pts.push(o, p);
  }
  for (let i = 0; i < 4; i++) pts.push(hit[i], hit[(i + 1) % 4]);
  frustum.geometry.dispose();
  frustum.geometry = new THREE.BufferGeometry().setFromPoints(pts);
}

function setCamera({ a, e, d, T, sx = 0 }) {
  const ar = (a * Math.PI) / 180, er = (e * Math.PI) / 180;
  // sx > 0 slides the subject right on screen by aiming left of it.
  T = [T[0] + sx * Math.sin(ar), T[1] - sx * Math.cos(ar), T[2]];
  camera.position.set(T[0] + d * Math.cos(er) * Math.cos(ar), T[1] + d * Math.cos(er) * Math.sin(ar), T[2] + d * Math.sin(er));
  camera.lookAt(T[0], T[1], T[2]);
  camera.updateMatrixWorld();
}
function toScreen(p) {
  const v = new THREE.Vector3(...p).project(camera);
  return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H];
}
function tipOf(q) {
  return K.fk(q, [0, 0, D.tip, 0, 0, 0]);
}

// ---------------------------------------------------------------- 2D helpers
function text(s, x, y, o = {}) {
  g.save();
  g.globalAlpha *= o.alpha ?? 1;
  g.font = `${o.weight || 700} ${o.size || 28}px ${o.font || UI}`;
  g.fillStyle = o.color || C.white;
  g.textAlign = o.align || "left";
  g.textBaseline = o.base || "alphabetic";
  if (o.upper) s = s.toUpperCase();
  if (o.spacing) g.letterSpacing = `${o.spacing}px`;
  g.fillText(s, x, y);
  g.restore();
}
function wrap(s, maxW, size, weight = 600, font = UI) {
  g.font = `${weight} ${size}px ${font}`;
  const words = s.split(" "), lines = [];
  let cur = "";
  for (const w of words) {
    const t = cur ? cur + " " + w : w;
    if (g.measureText(t).width > maxW && cur) lines.push(cur), (cur = w);
    else cur = t;
  }
  if (cur) lines.push(cur);
  return lines;
}
function panel(x, y, w, h, alpha = 1, r = 22) {
  g.save();
  g.globalAlpha *= alpha;
  g.fillStyle = C.panel;
  g.strokeStyle = "rgba(105,179,231,.28)";
  g.lineWidth = 1.5;
  g.beginPath();
  g.roundRect(x, y, w, h, r);
  g.fill();
  g.stroke();
  g.restore();
}
function caption(s, alpha) {
  if (alpha <= 0) return;
  const lines = wrap(s, 1240, 34, 600);
  const h = lines.length * 46 + 34;
  const y = H - 70 - h;
  panel(W / 2 - 680, y, 1360, h, alpha, 20);
  lines.forEach((l, i) => text(l, W / 2, y + 52 + i * 46, { size: 34, weight: 600, align: "center", alpha }));
}
function tag(world, label, sub, alpha = 1, dx = 70, dy = -70) {
  if (alpha <= 0) return;
  const [x, y] = toScreen(world);
  const tx = x + dx, ty = y + dy;
  g.save();
  g.globalAlpha = alpha;
  g.strokeStyle = C.sky;
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(x, y);
  g.lineTo(tx, ty);
  g.lineTo(tx + (dx >= 0 ? 24 : -24), ty);
  g.stroke();
  g.fillStyle = C.sky;
  g.beginPath();
  g.arc(x, y, 5, 0, Math.PI * 2);
  g.fill();
  g.restore();
  const ax = dx >= 0 ? "left" : "right";
  const lx = tx + (dx >= 0 ? 32 : -32);
  text(label, lx, ty + 9, { size: 28, weight: 800, align: ax, alpha });
  if (sub) text(sub, lx, ty + 42, { size: 22, weight: 500, color: C.ink2, align: ax, alpha });
}
function code(lines, x, y, alpha, hl = -1, w = 860) {
  if (alpha <= 0) return;
  const lh = 38;
  panel(x, y, w, lines.length * lh + 40, alpha, 16);
  lines.forEach((l, i) => {
    if (i === hl) {
      g.save();
      g.globalAlpha = alpha * 0.9;
      g.fillStyle = "rgba(203,51,59,.28)";
      g.fillRect(x + 8, y + 18 + i * lh, w - 16, lh);
      g.restore();
    }
    text(l, x + 28, y + 46 + i * lh, { size: 24, weight: 400, font: MONO, color: l.trim().startsWith("#") ? C.muted : C.white, alpha });
  });
}
function readout(label, values, x, y, alpha, digits = 1, unit = "") {
  if (alpha <= 0) return;
  text(label, x, y, { size: 22, weight: 800, color: C.sky, alpha, spacing: 1 });
  text(values.map((v) => v.toFixed(digits)).join("  ") + unit, x, y + 36, { size: 28, weight: 400, font: MONO, alpha });
}

// Camera image panel (upright view, 640 × 400 px).
function imagePanel(x, y, w, alpha, draw, zoom = null) {
  if (alpha <= 0) return;
  const h = (w * 400) / 640;
  const s = (w / 640) * (zoom?.k || 1);
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = "#0b1426";
  g.fillRect(x, y, w, h);
  g.strokeStyle = "rgba(105,179,231,.12)";
  g.lineWidth = 1;
  for (let u = 0; u <= 640; u += 80) {
    g.beginPath();
    g.moveTo(x + u * s, y);
    g.lineTo(x + u * s, y + h);
    g.stroke();
  }
  for (let v = 0; v <= 400; v += 80) {
    g.beginPath();
    g.moveTo(x, y + v * s);
    g.lineTo(x + w, y + v * s);
    g.stroke();
  }
  g.strokeStyle = C.blueHi;
  g.lineWidth = 3;
  g.strokeRect(x, y, w, h);
  g.restore();
  text(zoom ? `camera image, zoomed ×${zoom.k} around the aim` : "camera image · 640 × 400 px (shown upright)", x, y - 16, { size: 22, weight: 700, color: C.ink2, alpha });
  const [cu, cv] = zoom ? toUpright(zoom.at) : [320, 200];
  const P = (px) => {
    const [u, v] = toUpright(px);
    return [x + w / 2 + (u - cu) * s, y + h / 2 + (v - cv) * s];
  };
  g.save();
  g.beginPath();
  g.rect(x, y, w, h);
  g.clip();
  if (zoom) {
    // A 10-pixel grid, so the zoomed motion can be read in image pixels.
    g.strokeStyle = "rgba(105,179,231,.22)";
    g.lineWidth = 1;
    for (let k = -80; k <= 80; k += 10) {
      g.beginPath();
      g.moveTo(x + w / 2 + k * s, y);
      g.lineTo(x + w / 2 + k * s, y + h);
      g.moveTo(x, y + h / 2 + k * s);
      g.lineTo(x + w, y + h / 2 + k * s);
      g.stroke();
    }
    text("grid = 10 px", x + w - 14, y + h - 14, { size: 20, weight: 700, color: C.muted, align: "right", alpha });
  }
  draw({ P, s, x, y, w, h });
  g.restore();
}
function dotAt(P, px, alpha, r = 11, color = C.green) {
  const [a, b] = P(px);
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = color;
  g.beginPath();
  g.arc(a, b, r, 0, Math.PI * 2);
  g.fill();
  g.restore();
}
function reticle(P, px, alpha, label = "cup aim") {
  const [a, b] = P(px);
  g.save();
  g.globalAlpha = alpha;
  g.strokeStyle = C.red;
  g.lineWidth = 3;
  g.beginPath();
  g.moveTo(a - 22, b);
  g.lineTo(a + 22, b);
  g.moveTo(a, b - 22);
  g.lineTo(a, b + 22);
  g.stroke();
  g.beginPath();
  g.arc(a, b, 14, 0, Math.PI * 2);
  g.stroke();
  g.restore();
  if (label) text(label, a + 24, b - 18, { size: 22, weight: 800, color: C.red, alpha });
}
function matrix(M, x, y, alpha, label, digits = 2) {
  if (alpha <= 0) return;
  text(label, x, y, { size: 26, weight: 800, color: C.sky, alpha });
  const cw = 150;
  g.save();
  g.globalAlpha = alpha;
  g.strokeStyle = C.white;
  g.lineWidth = 3;
  const top = y + 18, hgt = 2 * 46 + 10, right = x + 12 + M[0].length * cw;
  g.beginPath();
  g.moveTo(x + 12, top);
  g.lineTo(x, top);
  g.lineTo(x, top + hgt);
  g.lineTo(x + 12, top + hgt);
  g.moveTo(right - 12, top);
  g.lineTo(right, top);
  g.lineTo(right, top + hgt);
  g.lineTo(right - 12, top + hgt);
  g.stroke();
  g.restore();
  M.forEach((row, r) => row.forEach((v, c) => text((v >= 0 ? " " : "") + v.toFixed(digits), x + 24 + c * cw, y + 64 + r * 46, { size: 30, weight: 400, font: MONO, alpha })));
}
function lamp(x, y, label, on, alpha, color = C.red) {
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = on ? color : "#1a2236";
  g.strokeStyle = "rgba(255,255,255,.25)";
  g.beginPath();
  g.arc(x, y, 16, 0, Math.PI * 2);
  g.fill();
  g.stroke();
  g.restore();
  text(label, x + 30, y + 9, { size: 24, weight: 700, alpha });
  text(on ? "1" : "0", x - 5, y + 8, { size: 18, weight: 800, font: MONO, color: on ? "#fff" : C.muted, alpha });
}
function checklist(items, x, y, lt, start, step, alpha) {
  items.forEach((s, i) => {
    const a = alpha * seg(lt, start + i * step, start + i * step + 0.4);
    if (a <= 0) return;
    g.save();
    g.globalAlpha = a;
    g.fillStyle = C.green;
    g.beginPath();
    g.arc(x + 14, y - 9 + i * 54, 13, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = "#04140a";
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(x + 7, y - 9 + i * 54);
    g.lineTo(x + 12, y - 3 + i * 54);
    g.lineTo(x + 21, y - 16 + i * 54);
    g.stroke();
    g.restore();
    text(s, x + 42, y + i * 54, { size: 28, weight: 600, alpha: a });
  });
}

// ---------------------------------------------------------------- precomputed poses
let P0 = {};
function poses() {
  const pick = D.pickupJoints;
  const watch = ik([...D.watch, D.cameraHeight], pick);
  const sampleQ = D.samples.map(([[dx, dy]]) => ik([D.watch[0] + dx, D.watch[1] + dy, D.cameraHeight], watch));
  const alignQ = D.align.map((s) => ik([...s.xy, D.cameraHeight], pick));
  const last = D.align.at(-1).xy;
  const approach = ik([...last, 94.35 + 15], alignQ.at(-1));
  const above = ik([...last, 99.4], approach);
  const contact = D.contactSteps.map((z) => ik([...last, z], above));
  const lift = ik([...last, 95.9 + 10], contact.at(-1));
  // Other wrist branch for the same tool pose (J4 + 180°, −J5, J6 + 180° as a
  // seed; numeric IK lands on the exact solution).
  const flipSeed = [pick[0], pick[1], pick[2], pick[3] + 180, -pick[4], pick[5] - 180];
  const flip = K.ik(K.fk(pick), flipSeed).joints;
  // Joint move vs straight line between the same two poses (scene "Or send
  // joint angles"), solved once with each step seeded from the last.
  const home = [0, 0, 0, 0, 0, 0];
  const A = K.fk(pick), B = K.fk(home);
  const wrap = (a, b) => ((((b - a) % 360) + 540) % 360) - 180;
  const jointPath = [], linePath = [];
  let seed = pick;
  for (let i = 0; i <= 60; i++) {
    const u = i / 60;
    jointPath.push(tipOf(lerpArr(pick, home, u)).slice(0, 3));
    const pose = A.map((v, k) => (k < 3 ? v + (B[k] - v) * u : v + wrap(v, B[k]) * u));
    seed = K.ik(pose, seed).joints;
    linePath.push(tipOf(seed).slice(0, 3));
  }
  P0 = { home, pick, watch, sampleQ, alignQ, approach, above, contact, lift, flip, last, jointPath, linePath };
}

// ---------------------------------------------------------------- scenes
const SCENES = [];
function sceneDef(def) {
  SCENES.push(def);
}

const camHero = { a: -35, e: 18, d: 1500, T: [180, 0, 220] };

sceneDef({
  name: "Title",
  dur: 7,
  three(lt) {
    return { q: jointKeys(lt, [[0, P0.home], [7, P0.pick]]), cam: camKeys(lt, [[0, { a: -60, e: 14, d: 1700, T: [120, 0, 220], sx: 420 }], [7, { ...camHero, sx: 420 }]]) };
  },
  draw(lt) {
    const a = win(lt, 0.3, 7);
    text("Louisiana Tech · Lite 6 lab", 120, 300, { size: 30, weight: 800, color: C.sky, alpha: a, spacing: 2 });
    text("How the arm sees", 120, 400, { size: 96, weight: 900, alpha: a });
    text("and how it moves", 120, 500, { size: 96, weight: 900, alpha: a, color: C.white });
    text("Calibration, from pixels to millimeters, and what we send to the SDK", 120, 580, { size: 34, weight: 500, color: C.ink2, alpha: a });
  },
});

sceneDef({
  name: "The cell",
  title: "Meet the cell",
  dur: 16,
  three(lt) {
    return { q: P0.pick, cam: camKeys(lt, [[0, { ...camHero, sx: 420 }], [16, { a: 25, e: 22, d: 1250, T: [200, 20, 200] }]]), block: [290, 20] };
  },
  draw(lt) {
    const q = P0.pick;
    const f = K.linkFrames(q);
    tag([f[3][3], f[3][7], f[3][11]], "UFACTORY Lite 6", "six-axis arm, base fixed to the table", win(lt, 0.6, 15.5), -260, -60);
    const tipP = tipOf(q);
    tag([tipP[0], tipP[1], tipP[2] + 20], "Vacuum gripper", "cup tip 61 mm past the flange", win(lt, 2.5, 15.5), 200, -40);
    const cam = new THREE.Vector3().setFromMatrixPosition(robot.camGroup.matrixWorld);
    tag([cam.x, cam.y, cam.z], "OAK-D Pro PoE", "wrist camera on a ring stand", win(lt, 4.5, 15.5), -260, 70);
    tag([292, 21, 34], "Green block", "the target; a green dot on top", win(lt, 6.5, 15.5), 200, -60);
    caption("Everything is measured from the robot's base, in millimeters. The camera rides on the gripper, so it moves with the tool.", win(lt, 8.5, 15.8));
  },
});

sceneDef({
  name: "Base frame",
  title: "Where is “here”? The base frame",
  dur: 18,
  three(lt) {
    return { q: P0.pick, cam: { a: -30, e: 24, d: 1350, T: [160, 0, 160] }, axes: true, flange: lt > 7 };
  },
  draw(lt) {
    const a = win(lt, 0.4, 17.6);
    tag([290, 0, 0], "+X forward", "away from the base", win(lt, 0.8, 17.6), 40, 60);
    tag([0, 290, 0], "+Y left", "", win(lt, 1.6, 17.6), -60, 50);
    tag([0, 0, 290], "+Z up", "", win(lt, 2.4, 17.6), 60, -20);
    const p = K.fk(P0.pick);
    panel(1220, 140, 600, 320, win(lt, 7, 17.6));
    readout("TOOL POSITION (mm)", p.slice(0, 3), 1260, 200, win(lt, 7, 17.6), 1);
    readout("ORIENTATION (deg) roll pitch yaw", p.slice(3), 1260, 300, win(lt, 8, 17.6), 1);
    text("get_position() → [x, y, z, roll, pitch, yaw]", 1260, 420, { size: 22, weight: 500, font: MONO, color: C.ink2, alpha: win(lt, 9, 17.6) });
    caption(
      lt < 7
        ? "The controller answers every position question in one frame: X forward, Y to the left, Z up, measured from the base."
        : "A pose is six numbers: where the tool is, and which way it points. Ours reports the flange (TCP offset 0); the cup tip is 61 mm further along the tool axis.",
      Math.min(a, lt < 7 ? win(lt, 0.4, 7) : win(lt, 7, 17.6)),
    );
  },
});

const JOINT_DEMO = (lt) => {
  const q = P0.pick.slice();
  const j = Math.min(5, Math.floor(lt / 3));
  const u = (lt - j * 3) / 3;
  q[j] += 25 * Math.sin(u * Math.PI * 2) * ease(Math.min(1, u * 4)) * ease(Math.min(1, (1 - u) * 4));
  return { q, j };
};
sceneDef({
  name: "Joints",
  title: "Six joints make one pose",
  dur: 20,
  three(lt) {
    return { q: lt < 18 ? JOINT_DEMO(lt).q : P0.pick, cam: { a: 10, e: 20, d: 1250, T: [170, 0, 230] }, flange: true, highlight: lt < 18 ? JOINT_DEMO(lt).j + 1 : -1 };
  },
  draw(lt) {
    const { q, j } = JOINT_DEMO(Math.min(lt, 17.99));
    const a = win(lt, 0.3, 19.6);
    panel(1260, 130, 560, 470, a);
    text("JOINT ANGLES (deg)", 1300, 190, { size: 22, weight: 800, color: C.sky, alpha: a, spacing: 1 });
    q.forEach((v, i) => {
      const on = i === j && lt < 18;
      text(`J${i + 1}`, 1300, 245 + i * 50, { size: 30, weight: 900, color: on ? C.red : C.white, alpha: a });
      text(v.toFixed(1).padStart(7), 1400, 245 + i * 50, { size: 30, weight: 400, font: MONO, color: on ? C.red : C.white, alpha: a });
    });
    const p = K.fk(q);
    text(`tool  ${p.slice(0, 3).map((v) => v.toFixed(0)).join(", ")} mm`, 1300, 570, { size: 24, weight: 500, font: MONO, color: C.ink2, alpha: a });
    caption(
      lt < 9
        ? "Each joint turns about its own axis. Turning one joint moves everything after it, so the tool's position depends on all six angles."
        : lt < 18
          ? "Forward kinematics: multiply the six joint transforms in order, T = T₁(J1)·T₂(J2)···T₆(J6), and read the tool pose off the end."
          : "Six numbers in, one pose out. The controller does this every few milliseconds.",
      a,
    );
  },
});

sceneDef({
  name: "Kinematics fit",
  title: "Every arm is a little different",
  dur: 14,
  three(lt) {
    return { q: P0.pick, cam: { a: -10, e: 16, d: 1100, T: [200, 0, 200] }, ghostA: P0.pick, ghostOffset: 100 * ease(seg(lt, 1, 4)) * (1 - ease(seg(lt, 6, 8))) };
  },
  draw(lt) {
    const a = win(lt, 0.3, 13.6);
    panel(1240, 150, 580, 360, a);
    text("PUBLISHED vs THIS ARM", 1280, 210, { size: 22, weight: 800, color: C.sky, alpha: a, spacing: 1 });
    text(`${D.kinFit.nominal} mm`, 1280, 290, { size: 64, weight: 900, color: C.gold, alpha: a });
    text("worst error, published geometry", 1280, 330, { size: 24, weight: 500, color: C.ink2, alpha: a });
    text(`${D.kinFit.fitted} mm`, 1280, 420, { size: 64, weight: 900, color: C.green, alpha: win(lt, 6, 13.6) });
    text(`after fitting ${D.kinFit.samples} controller answers`, 1280, 460, { size: 24, weight: 500, color: C.ink2, alpha: win(lt, 6, 13.6) });
    tag([290, 120, 330], "published model", "offset shown 10× larger", win(lt, 1.5, 6), -470, -150);
    caption(
      lt < 6
        ? "The arm's published dimensions are nominal. Each controller carries its own factory calibration, so the textbook model was up to 10 mm off."
        : "We asked the controller for its own forward kinematics at 300 random angles (pure math, no motion) and fitted the model's joint origins to match.",
      a,
    );
  },
});

sceneDef({
  name: "Orientation",
  title: "Roll, pitch, yaw",
  dur: 15,
  three(lt) {
    const p = K.fk(P0.pick);
    const roll = lerp(-120, p[3], ease(seg(lt, 1, 6))); // the short way round
    const q = K.ik([p[0], p[1], p[2], roll, p[4], p[5]], P0.pick).joints;
    return { q, cam: { a: 40, e: 14, d: 900, T: [270, 20, 230] }, flange: true };
  },
  draw(lt) {
    const a = win(lt, 0.3, 14.6);
    panel(1200, 160, 650, 300, a);
    text("R = Rz(yaw)·Ry(pitch)·Rx(roll)", 1240, 230, { size: 28, weight: 700, font: MONO, alpha: a });
    text("fixed axes, applied roll first", 1240, 272, { size: 24, weight: 500, color: C.ink2, alpha: a });
    text("roll ≈ 180°  → cup points down", 1240, 340, { size: 26, weight: 700, color: C.green, alpha: win(lt, 6, 14.6) });
    text("pitch ≈ 0°, yaw ≈ 0°  → level, square", 1240, 384, { size: 26, weight: 700, color: C.green, alpha: win(lt, 7, 14.6) });
    caption("The three angles say which way the tool faces. Every pick uses the same orientation: cup straight down, so only X, Y and Z change.", win(lt, 1, 14.6));
  },
});

sceneDef({
  name: "Camera view",
  title: "What the camera sees",
  dur: 16,
  three() {
    return { q: P0.pick, cam: { a: -50, e: 30, d: 1150, T: [330, 20, 120] }, frustum: true, block: [290 + 2, 20 + 0.7] };
  },
  draw(lt) {
    const a = win(lt, 0.3, 15.6);
    imagePanel(1060, 190, 780, a, ({ P }) => {
      dotAt(P, D.firstFit.aim, a * win(lt, 3, 15.6));
      if (lt > 6) text("centroid (330, 59) px", ...P(D.firstFit.aim).map((v, i) => v + (i ? 50 : -120)), { size: 24, weight: 800, color: C.green, alpha: win(lt, 6, 15.6) });
    });
    panel(1060, 720, 780, 130, win(lt, 8, 15.6), 16);
    text("HSV:  hue 35–85, saturation ≥ 80, value ≥ 55", 1090, 770, { size: 24, weight: 400, font: MONO, alpha: win(lt, 8, 15.6) });
    text("mask → clean up → biggest blob ≥ 300 px² → centroid", 1090, 815, { size: 24, weight: 400, font: MONO, color: C.ink2, alpha: win(lt, 9, 15.6) });
    caption(
      lt < 8
        ? "The camera looks down past the cup. Its picture is 640 × 400 pixels, and the green dot shows up as a pixel position, not a distance."
        : "Color detection keeps pixels whose hue and saturation look green, removes specks, and reports the blob's center in pixels.",
      a,
    );
  },
});

sceneDef({
  name: "Cup aim",
  title: "The cup's aim point",
  dur: 16,
  three(lt) {
    const z = lt < 5 ? lerp(88.35 + 2, D.cameraHeight, ease(seg(lt, 1.5, 5))) : D.cameraHeight;
    const q = ik([...D.watch, z], P0.watch);
    return { q, cam: { a: -70, e: 18, d: 1000, T: [D.watch[0], D.watch[1], 150] }, block: [D.watch[0] + 2, D.watch[1] + 0.7], frustum: lt > 5 };
  },
  draw(lt) {
    const a = win(lt, 0.3, 15.6);
    imagePanel(1060, 190, 780, win(lt, 5, 15.6), ({ P }) => {
      dotAt(P, D.samples[0][1], win(lt, 5.5, 15.6));
      reticle(P, D.firstFit.aim, win(lt, 7, 15.6));
    });
    caption(
      lt < 5
        ? "Teaching: the operator lowered the cup onto the block by hand until the vacuum sealed. Then the arm rose straight up to camera height."
        : "Straight above the block, the dot sits at about (330, 59). That pixel becomes the cup aim: if the dot is there, the cup is right above it.",
      a,
    );
  },
});

const SAMPLE_T = 1.6; // seconds per sample
sceneDef({
  name: "Sampling",
  title: "Calibration, step 1: move and look",
  dur: 2 + D.samples.length * SAMPLE_T + 4,
  three(lt) {
    const k = clamp(Math.floor((lt - 2) / SAMPLE_T), 0, D.samples.length - 1);
    const u = ease(seg(lt - 2 - k * SAMPLE_T, 0, 0.7));
    const q = lerpArr(P0.sampleQ[Math.max(0, k - 1)], P0.sampleQ[k], k === 0 ? 1 : u);
    return { q: lt < 2 ? P0.sampleQ[0] : q, cam: { a: -80, e: 34, d: 1150, T: [D.watch[0] + 20, D.watch[1], 160], sx: -260 }, block: [D.watch[0] + 2, D.watch[1] + 0.7], frustum: true, flange: true };
  },
  draw(lt) {
    const a = win(lt, 0.3, this.dur - 0.4);
    const k = clamp(Math.floor((lt - 2) / SAMPLE_T), -1, D.samples.length - 1);
    imagePanel(1100, 130, 720, a, ({ P }) => {
      reticle(P, D.firstFit.aim, a * 0.5, "");
      for (let i = 0; i <= k; i++) dotAt(P, D.samples[i][1], a * (i === k ? 1 : 0.45), i === k ? 13 : 9);
      if (k >= 0) {
        const [[dx, dy]] = D.samples[k];
        const [px, py] = P(D.samples[k][1]);
        text(`arm ${dx >= 0 ? "+" : ""}${dx}, ${dy >= 0 ? "+" : ""}${dy} mm`, px + 18, py - 16, { size: 22, weight: 800, color: C.green, alpha: a });
      }
    }, { k: 6, at: D.firstFit.aim });
    panel(1100, 600, 720, 230, a, 16);
    text("offset (mm)        dot (px)", 1130, 645, { size: 22, weight: 800, color: C.sky, alpha: a, font: MONO });
    const first = Math.max(0, k - 3);
    for (let i = first; i <= k; i++) {
      const [[dx, dy], [u, v]] = D.samples[i];
      text(`${String(dx).padStart(4)}, ${String(dy).padStart(4)}     ${u.toFixed(1)}, ${v.toFixed(1)}`, 1130, 685 + (i - first) * 38, { size: 24, weight: 400, font: MONO, color: i === k ? C.white : C.muted, alpha: a });
    }
    caption(
      lt < 2 + 5 * SAMPLE_T
        ? "At one fixed height, the arm visits a 20 mm square: ±10 mm in X and Y, nine spots plus a return to the middle. At each stop it waits for three steady frames and records where the dot appears."
        : "The block never moves; the camera does. So the dot slides across the image opposite to the arm. The last stop repeats the first, to prove nothing shifted (0.4 px apart).",
      a,
    );
  },
});

sceneDef({
  name: "Fit",
  title: "Calibration, step 2: fit the response",
  dur: 20,
  three() {
    return { q: P0.sampleQ[0], cam: { a: -80, e: 34, d: 1150, T: [D.watch[0] + 20, D.watch[1], 160], sx: -260 }, block: [D.watch[0] + 2, D.watch[1] + 0.7], frustum: true };
  },
  draw(lt) {
    const a = win(lt, 0.3, 19.6);
    panel(90, 130, 1000, 560, a);
    text("pixel  =  aim  +  J · (Δx, Δy)", 140, 220, { size: 44, weight: 800, font: MONO, alpha: a });
    text("20 equations (10 stops × 2), 6 unknowns → least squares", 140, 270, { size: 26, weight: 500, color: C.ink2, alpha: win(lt, 2, 19.6) });
    matrix(D.firstFit.J, 140, 340, win(lt, 4, 19.6), "J  (pixels per mm)");
    text(`aim = (${D.firstFit.aim.map((v) => v.toFixed(1)).join(", ")}) px`, 140, 530, { size: 28, weight: 400, font: MONO, alpha: win(lt, 5, 19.6) });
    panel(1140, 130, 700, 560, win(lt, 7, 19.6));
    text("ACCEPTED ONLY IF", 1180, 190, { size: 22, weight: 800, color: C.sky, alpha: win(lt, 7, 19.6), spacing: 1 });
    checklist(
      [`fit residual ${D.firstFit.residual} px  (≤ 2)`, `condition ${D.firstFit.condition}  (≤ 5)`, "start and end agree  (≤ 2 px)", "3 untouched check points  (≤ 2 px)", "response strong enough  (σ ≥ 0.25)"],
      1180,
      260,
      lt,
      7.5,
      0.7,
      win(lt, 7, 19.6),
    );
    caption(
      lt < 11
        ? "J is a 2 × 2 grid of numbers: how many pixels the dot moves for each millimeter the arm moves in X and in Y."
        : lt < 16
          ? "Here 1 mm forward moves the dot about 2 px up the picture, and 1 mm left moves it about 2 px across: the camera is turned 90° on its stand, so the axes swap."
          : `The pickup profile was re-measured the same way at today's pickup spot: J ≈ [[0.10, −1.69], [−1.85, −0.12]] px/mm, ${D.profile.residual} px fit, ${D.profile.holdout} px on held-out points.`,
      a,
    );
  },
});

const ALIGN_T = 3.2;
sceneDef({
  name: "Align",
  title: "Using it: pixels → a move",
  dur: 2 + D.align.length * ALIGN_T + 4,
  three(lt) {
    const k = clamp(Math.floor((lt - 2) / ALIGN_T), 0, D.align.length - 1);
    const u = ease(seg(lt - 2 - k * ALIGN_T, 1.6, 2.8));
    const q = k < D.align.length - 1 ? lerpArr(P0.alignQ[k], P0.alignQ[k + 1], u) : P0.alignQ.at(-1);
    const b = D.align.at(-1).xy;
    return { q: lt < 2 ? P0.alignQ[0] : q, cam: { a: -60, e: 40, d: 1000, T: [340, 10, 120] }, block: [b[0] + 2, b[1] + 0.7], frustum: true };
  },
  draw(lt) {
    const a = win(lt, 0.3, this.dur - 0.4);
    const k = clamp(Math.floor((lt - 2) / ALIGN_T), 0, D.align.length - 1);
    const s = D.align[k];
    imagePanel(1080, 140, 760, a, ({ P }) => {
      reticle(P, D.profile.aim, a);
      for (let i = 0; i < k; i++) dotAt(P, D.align[i].px, a * 0.35, 7);
      dotAt(P, s.px, a);
    });
    panel(1080, 650, 760, 300, a, 16);
    const err = Math.hypot(...s.err);
    text(`step ${k + 1}`, 1110, 700, { size: 24, weight: 800, color: C.sky, alpha: a });
    text(`${err.toFixed(1)} mm`, 1110, 780, { size: 64, weight: 900, color: err < 1 ? C.green : C.gold, alpha: a });
    text("still to go", 1110, 818, { size: 22, weight: 500, color: C.ink2, alpha: a });
    text("Δmm = 0.9 · J⁻¹ (aim − dot)", 1450, 720, { size: 24, weight: 700, font: MONO, alpha: a });
    text("cap 60 mm, then look again", 1450, 760, { size: 22, weight: 500, color: C.ink2, alpha: a });
    text("done when < 0.75 mm", 1450, 800, { size: 22, weight: 500, color: C.ink2, alpha: a });
    caption(
      lt < 2 + ALIGN_T
        ? "A real pick from today: the dot started far from the aim. Turn the pixel gap into millimeters with J, move 90% of the way, then look again."
        : lt < 2 + 3 * ALIGN_T
          ? "104 mm, then 40, then 1.7: each look corrects the last move. Every step also checks the image moved the way J predicts, or the cycle stops."
          : "Half a millimeter. Now the cup is directly above the dot, and only Z needs to change.",
      a,
    );
  },
});

sceneDef({
  name: "One height",
  title: "Why it only works at one height",
  dur: 14,
  three(lt) {
    const z = D.cameraHeight - 90 * Math.sin(ease(seg(lt, 2, 9)) * Math.PI);
    const b = D.align.at(-1).xy;
    return { q: ik([...b, z], P0.alignQ.at(-1)), cam: { a: -20, e: 10, d: 1050, T: [360, 0, 160] }, block: [b[0] + 2, b[1] + 0.7], frustum: true };
  },
  draw(lt) {
    const a = win(lt, 0.3, 13.6);
    const z = D.cameraHeight - 90 * Math.sin(ease(seg(lt, 2, 9)) * Math.PI);
    const dist = z - 33.35 + 18;
    const pxmm = 381 / dist;
    panel(1250, 170, 570, 300, a);
    text("pixels per mm ≈ focal length ÷ distance", 1290, 230, { size: 26, weight: 700, alpha: a });
    text(`${pxmm.toFixed(2)} px/mm`, 1290, 330, { size: 72, weight: 900, color: Math.abs(z - D.cameraHeight) < 3 ? C.green : C.gold, alpha: a });
    text(`camera ${dist.toFixed(0)} mm above the block`, 1290, 380, { size: 24, weight: 500, color: C.ink2, alpha: a });
    caption("Closer means bigger: the same millimeter covers more pixels. J was measured at one height and one orientation, so every pick starts from that same camera pose.", win(lt, 1, 13.6));
  },
});

sceneDef({
  name: "set_position",
  title: "Writing a position to the SDK",
  dur: 20,
  three(lt) {
    const b = D.align.at(-1).xy;
    const prof = trapezoid(lt - 6, D.cameraHeight - (94.35 + 15), 60, 200);
    const z = lerp(D.cameraHeight, 94.35 + 15, lt < 6 ? 0 : prof.s);
    return { q: ik([...b, z], P0.alignQ.at(-1)), cam: { a: -35, e: 14, d: 1150, T: [360, 0, 190], sx: 430 }, block: [b[0] + 2, b[1] + 0.7], flange: true, trail: lt > 6 ? [[...b, D.cameraHeight], [...b, z]] : null };
  },
  draw(lt) {
    const a = win(lt, 0.3, 19.6);
    code(
      [
        "# straight down to 15 mm above the block",
        "code = arm.set_position(",
        "    x=382.9, y=-6.0, z=109.4,",
        "    roll=-179.4, pitch=-2.05, yaw=2.48,",
        "    speed=60, mvacc=200,        # mm/s, mm/s²",
        "    is_radian=False, wait=True)",
        "assert code == 0               # 0 = accepted and done",
        "pose = arm.get_position()[1]   # read it back",
      ],
      80,
      130,
      a,
      lt < 6 ? Math.min(7, Math.floor(lt)) : lt < 12 ? 4 : 7,
      880,
    );
    // Speed profile plot.
    const prof = trapezoid(lt - 6, D.cameraHeight - (94.35 + 15), 60, 200);
    const px = 80, py = 500, pw = 880, ph = 200;
    const pa = win(lt, 6, 19.6);
    panel(px, py, pw, ph + 70, pa, 16);
    text("speed (mm/s) vs time", px + 28, py + 40, { size: 22, weight: 800, color: C.sky, alpha: pa });
    g.save();
    g.globalAlpha = pa;
    g.strokeStyle = C.sky;
    g.lineWidth = 3;
    g.beginPath();
    for (let i = 0; i <= 200; i++) {
      const t = (i / 200) * prof.total;
      const sp = trapezoid(t, D.cameraHeight - (94.35 + 15), 60, 200).speed;
      const X = px + 40 + (t / prof.total) * (pw - 80), Y = py + ph + 20 - (sp / 70) * (ph - 60);
      i ? g.lineTo(X, Y) : g.moveTo(X, Y);
    }
    g.stroke();
    const tt = clamp(lt - 6, 0, prof.total);
    g.fillStyle = C.red;
    g.beginPath();
    g.arc(px + 40 + (tt / prof.total) * (pw - 80), py + ph + 20 - (trapezoid(tt, D.cameraHeight - 109.35, 60, 200).speed / 70) * (ph - 60), 9, 0, Math.PI * 2);
    g.fill();
    g.restore();
    caption(
      lt < 6
        ? "To move in a straight line we send a pose: six numbers plus speed and acceleration. The controller works out the joint angles itself, many times a second, all along the line."
        : lt < 12
          ? "It speeds up at mvacc, cruises at speed, and slows down to stop exactly on the target: a trapezoid. wait=True means the call returns when the move is finished."
          : "Then we read the position back and check it is within 0.3 mm of what we asked for. A nonzero return code stops the cycle; nothing retries blindly.",
      a,
    );
  },
});

sceneDef({
  name: "set_servo_angle",
  title: "Or send joint angles",
  dur: 18,
  three(lt) {
    const u = ease(seg(lt, 4, 12));
    return {
      q: lerpArr(P0.pick, P0.home, u),
      cam: { a: -75, e: 12, d: 1150, T: [190, 10, 170], sx: 330 },
      pathA: P0.jointPath,
      pathB: lt > 12 ? P0.linePath : null,
    };
  },
  draw(lt) {
    const a = win(lt, 0.3, 17.6);
    code(
      [
        "# every joint to a target angle, together",
        "code = arm.set_servo_angle(",
        "    angle=[0, 0, 0, 0, 0, 0],   # degrees",
        "    speed=25, mvacc=60,         # deg/s, deg/s²",
        "    is_radian=False, wait=True)",
      ],
      80,
      130,
      a,
      lt < 4 ? 2 : 3,
      860,
    );
    text("joint move: the tool path curves", 80, 470, { size: 28, weight: 800, color: C.sky, alpha: win(lt, 6, 17.6) });
    text("straight-line move between the same poses", 80, 515, { size: 28, weight: 800, color: C.gold, alpha: win(lt, 12, 17.6) });
    caption(
      lt < 12
        ? "set_servo_angle interpolates the joints, not the tool. All six start and stop together, and the tool sweeps a curve: often the safest way to travel long distances."
        : "set_position would have kept the tool on a straight line instead. Pick the one whose path you have checked; the deck previews every path before it moves.",
      a,
    );
  },
});

sceneDef({
  name: "IK branches",
  title: "Same pose, two ways to hold it",
  dur: 15,
  three() {
    return { q: P0.pick, hideRobot: true, ghostA: P0.pick, ghostB: P0.flip, cam: { a: 120, e: 14, d: 1350, T: [220, 20, 300], sx: -150 } };
  },
  draw(lt) {
    const a = win(lt, 0.3, 14.6);
    const fa = P0.pick, fb = P0.flip;
    panel(1180, 160, 640, 260, a);
    text(`J4 ${fa[3].toFixed(0)}°, J5 ${fa[4].toFixed(0)}°, J6 ${fa[5].toFixed(0)}°`, 1220, 230, { size: 28, weight: 700, font: MONO, color: C.sky, alpha: a });
    text(`J4 ${fb[3].toFixed(0)}°, J5 ${fb[4].toFixed(0)}°, J6 ${fb[5].toFixed(0)}°`, 1220, 290, { size: 28, weight: 700, font: MONO, color: C.gold, alpha: a });
    text("→ identical cup position and angle", 1220, 360, { size: 26, weight: 600, color: C.ink2, alpha: a });
    caption(
      lt < 8
        ? "Inverse kinematics can have several answers. These two arms put the cup in exactly the same place; only the wrist is turned the other way round."
        : "Going from the hand demo to the pickup pose, the controller's own answer spun the wrist 238°, enough to wind up the camera cable. The deck stores the answer our pickups were tested on.",
      a,
    );
  },
});

const PICK_LOG = [
  [0.5, "set_position(z=99.4)  slow, 10 mm/s"],
  [2.0, "set_vacuum_gripper(True)  → DO0=1, DO1=0"],
  [3.2, "read outputs back: [1, 0]  ✓"],
  [4.2, "step 0.5 mm down, read seal ×3"],
  [9.5, "z 95.9: sealed  (DI0 = 1, feedback = 1)"],
  [11, "set_position(z=105.9)  lift 10 mm"],
  [12.5, "hold 0.5 s, seal read every 0.1 s"],
  [14, "set_vacuum_gripper(False) → DO0=0, DO1=1"],
  [15.2, "release verified: DI0 = 0"],
];
sceneDef({
  name: "Pickup",
  title: "The pickup, command by command",
  dur: 20,
  three(lt) {
    let q;
    if (lt < 2) q = lerpArr(P0.approach, P0.above, ease(seg(lt, 0.4, 2)));
    else if (lt < 9.5) {
      const k = clamp(Math.floor((lt - 4.2) / 0.7), 0, P0.contact.length - 1);
      q = lt < 4.2 ? P0.above : P0.contact[k];
    } else if (lt < 11) q = P0.contact.at(-1);
    else q = lerpArr(P0.contact.at(-1), P0.lift, ease(seg(lt, 11, 12.5)));
    const held = lt > 9.5 && lt < 14;
    const b = D.align.at(-1).xy;
    return { q, cam: { a: -40, e: 6, d: 560, T: [b[0], b[1], 110] }, block: [b[0] + 2, b[1] + 0.7], held, suction: lt > 2 && lt < 14 };
  },
  draw(lt) {
    const a = win(lt, 0.3, 19.6);
    panel(1180, 120, 660, 560, a);
    text("WHAT THE DECK SENDS", 1220, 180, { size: 22, weight: 800, color: C.sky, alpha: a, spacing: 1 });
    PICK_LOG.forEach(([t, s], i) => text(s, 1220, 230 + i * 48, { size: 22, weight: 400, font: MONO, color: lt > t ? C.white : "rgba(143,160,191,.35)", alpha: a }));
    panel(1180, 700, 660, 150, a, 16);
    const suction = lt > 2 && lt < 14;
    lamp(1230, 760, "DO0 suction", suction, a);
    lamp(1460, 760, "DO1 release", !suction, a, C.sky);
    lamp(1230, 815, "DI0 sealed", lt > 9.5 && lt < 15.2, a, C.green);
    const z = lt < 4.2 ? 99.4 : D.contactSteps[clamp(Math.floor((lt - 4.2) / 0.7), 0, D.contactSteps.length - 1)];
    if (lt > 4 && lt < 10) text(`z ${z.toFixed(1)}`, 1460, 822, { size: 28, weight: 800, font: MONO, color: C.gold, alpha: a });
    caption(
      lt < 4
        ? "Turn suction on before touching anything, and read the outputs back. On this arm a paired write can return OK yet leave both outputs low."
        : lt < 10
          ? "Then creep down half a millimeter at a time, reading the seal three times at each stop. Today it sealed on the eighth step, at z 95.9."
          : "Lift only once the seal is confirmed, keep checking it while holding, and verify the release input goes low before moving away.",
      a,
    );
  },
});

sceneDef({
  name: "Safety",
  title: "Before every move",
  dur: 16,
  three(lt) {
    return { q: P0.pick, cam: camKeys(lt, [[0, { a: -30, e: 20, d: 1300, T: [180, 0, 200], sx: 520 }], [16, { a: 10, e: 24, d: 1450, T: [180, 0, 200], sx: 560 }]]) };
  },
  draw(lt) {
    const a = win(lt, 0.3, 15.6);
    panel(90, 140, 920, 600, a);
    checklist(
      [
        "controller ready (state 2), no errors or warnings",
        "suction outputs read back as expected",
        "target inside the checked tabletop region",
        "whole path previewed: IK continuous, no joint limits",
        "speed and acceleration under the set caps",
        "fresh camera frame (< 0.5 s old)",
        "pose read back after the move (≤ 0.3 mm)",
      ],
      140,
      230,
      lt,
      1,
      1.1,
      a,
    );
    caption("Software checks decide whether to send the next command. They can't stop a move already running: the physical E-stop is the only immediate stop.", win(lt, 9, 15.6));
  },
});

sceneDef({
  name: "End",
  dur: 7,
  three(lt) {
    return { q: P0.pick, cam: camKeys(lt, [[0, { a: 10, e: 24, d: 1450, T: [180, 0, 200], sx: 560 }], [7, { a: 40, e: 20, d: 1700, T: [180, 0, 200], sx: 620 }]]) };
  },
  draw(lt) {
    const a = win(lt, 0.3, 7);
    text("Pixels → millimeters → commands", 120, 420, { size: 72, weight: 900, alpha: a });
    text("Measure the image response, close the loop, check before every move.", 120, 500, { size: 34, weight: 500, color: C.ink2, alpha: a });
    text("Try it yourself in the Lab tab: blocks on the left, a simulated Lite 6 on the right.", 120, 580, { size: 30, weight: 600, color: C.sky, alpha: a });
  },
});

let acc = 0;
for (const s of SCENES) {
  s.start = acc;
  acc += s.dur;
}
const TOTAL = acc;

// ---------------------------------------------------------------- render
const blockGhostZ = 0;
function render(t) {
  t = clamp(t, 0, TOTAL - 1e-3);
  const s = SCENES.find((x) => t < x.start + x.dur) || SCENES.at(-1);
  const lt = t - s.start;
  const st = s.three(lt);
  robot.set(st.q);
  robot.visible(!st.hideRobot);
  ghostA.visible(!!st.ghostA);
  ghostB.visible(!!st.ghostB);
  if (st.ghostA) {
    ghostA.set(st.ghostA);
    // Matrix4 is column-major: elements[13] is the Y translation.
    for (const l of ghostA.links) l.matrix.elements[13] += st.ghostOffset || 0;
  }
  if (st.ghostB) ghostB.set(st.ghostB);
  baseAxes.visible = !!st.axes;
  flangeAxes.visible = !!st.flange;
  if (st.flange) {
    flangeAxes.matrix.set(...K.linkFrames(st.q)[6]);
    flangeAxes.matrixWorldNeedsUpdate = true;
  }
  // Block: on the table, or carried under the cup.
  block.visible = !!st.block;
  if (st.block) {
    if (st.held) {
      const tip = tipOf(st.q);
      block.position.set(tip[0], tip[1], tip[2] - 33.35);
    } else block.position.set(st.block[0], st.block[1], blockGhostZ);
  }
  robot.cupTip.material.color.set(st.suction ? C.red : 0x1d2433);
  // Highlight a moving link.
  for (let i = 0; i < 7; i++) {
    const mesh = robot.links[i].children[0];
    mesh.material.emissive?.set(i === st.highlight ? 0x5a1015 : 0x000000);
  }
  setCamera(st.cam);
  updateFrustum(!!st.frustum);
  pathA.visible = !!(st.pathA || st.trail);
  if (st.pathA || st.trail) setLine(pathA, st.pathA || st.trail);
  pathB.visible = !!st.pathB;
  if (st.pathB) setLine(pathB, st.pathB);
  zone.visible = !!st.block;
  renderer.render(scene3, camera);

  g.clearRect(0, 0, W, H);
  // Vignette.
  const vg = g.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 0.95);
  vg.addColorStop(0, "rgba(0,0,0,0)");
  vg.addColorStop(1, "rgba(0,0,0,.55)");
  g.fillStyle = vg;
  g.fillRect(0, 0, W, H);
  if (s.title) {
    const n = SCENES.filter((x) => x.title).indexOf(s) + 1;
    const a = win(lt, 0.1, s.dur);
    text(String(n).padStart(2, "0"), 80, 92, { size: 30, weight: 900, color: C.red, alpha: a });
    text(s.title, 140, 92, { size: 40, weight: 900, alpha: a });
  }
  s.draw(lt);
  // Fade through black between scenes.
  const fade = Math.max(1 - seg(lt, 0, 0.35), seg(lt, s.dur - 0.35, s.dur));
  if (fade > 0) {
    g.fillStyle = `rgba(0,0,0,${fade})`;
    g.fillRect(0, 0, W, H);
  }
  // Progress bar.
  g.fillStyle = "rgba(255,255,255,.08)";
  g.fillRect(0, H - 6, W, 6);
  g.fillStyle = C.red;
  g.fillRect(0, H - 6, (t / TOTAL) * W, 6);
  return s.name;
}

// ---------------------------------------------------------------- player
function fit() {
  // The film is drawn at 1920 × 1080 and scaled to fit the window.
  const k = Math.min(innerWidth / W, innerHeight / H);
  stage.style.transform = `translate(-50%, -50%) scale(${k})`;
  stage.style.transformOrigin = "50% 50%";
}

async function boot() {
  try {
    const geo = await (await fetch("/api/lab-kinematics", { cache: "no-store" })).json();
    if (geo.joints) K.setGeometry(geo.joints);
  } catch (_) {}
  await loadGeoms();
  build3D();
  poses();
  document.getElementById("loading").remove();
  window.render = (t) => render(t);
  window.TOTAL = TOTAL;
  window.SCENES = SCENES.map((s) => ({ name: s.name, start: s.start, dur: s.dur }));
  fit();
  addEventListener("resize", fit);
  const player = document.getElementById("player");
  if (AUTO) {
    player.remove();
    render(0);
    return;
  }
  let t = 0;
  let playing = true;
  let last = performance.now();
  const scrub = document.getElementById("scrub");
  const clock = document.getElementById("clock");
  const name = document.getElementById("scene-name");
  const fmt = (x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
  const playBtn = document.getElementById("play");
  const setPlaying = (p) => {
    playing = p;
    playBtn.textContent = p ? "Pause" : "Play";
  };
  const jump = (x) => (t = clamp(x, 0, TOTAL - 0.01));
  playBtn.onclick = () => setPlaying(!playing);
  scrub.oninput = () => jump((scrub.value / 1000) * TOTAL);
  addEventListener("keydown", (e) => {
    const cur = SCENES.findIndex((x) => t < x.start + x.dur);
    if (e.key === " ") setPlaying(!playing), e.preventDefault();
    else if (e.key === "ArrowRight") jump(t + 5);
    else if (e.key === "ArrowLeft") jump(t - 5);
    else if (e.key === "n" || e.key === "PageDown") jump(SCENES[Math.min(SCENES.length - 1, cur + 1)].start);
    else if (e.key === "p" || e.key === "PageUp") jump(SCENES[Math.max(0, cur - 1)].start);
    else if (e.key === "r") jump(0);
  });
  stage.onclick = () => setPlaying(!playing);
  addEventListener("mousemove", (e) => player.classList.toggle("show", e.clientY > innerHeight - 120));
  setPlaying(true);
  const loop = (now) => {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (playing) t = (t + dt) % TOTAL;
    const sn = render(t);
    scrub.value = String(Math.round((t / TOTAL) * 1000));
    clock.textContent = `${fmt(t)} / ${fmt(TOTAL)}`;
    name.textContent = sn;
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}
boot();
