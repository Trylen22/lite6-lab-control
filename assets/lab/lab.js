/* Lab tab: Blockly on the left, a simulated Lite 6 on the right.
 *
 * SIMULATION ONLY. This module never sends anything to the robot; the only
 * request it makes to the arm side is reading telemetry (to copy the real
 * arm's current joints into the simulator when asked).
 *
 * Pieces: kinematics.js (FK/IK, calibrated per arm), program.js (blocks →
 * timeline), blocks.js (Studio-compatible blocks), studio-file.js (Studio
 * .tar.gz import/export). Meshes are UFACTORY's (xarm_ros2, BSD-3).
 */
import * as THREE from "three";
import { STLLoader } from "/assets/vendor/three-addons/STLLoader.js";
import { OrbitControls } from "/assets/vendor/three-addons/OrbitControls.js";

const K = window.Lite6;
const P = window.LabProgram;
const B = window.Blockly;
const $ = (id) => document.getElementById(id);

// Approximate lab geometry (robot mm). The pickup contact height is measured;
// the table and shelf are estimates for practice, not collision guarantees.
const BLOCK_SIZE = 40;
const BLOCK_TOP = 94.35; // measured contact height of the block top
const TABLE_Z = BLOCK_TOP - BLOCK_SIZE;
const SHELF = { name: "shelf (approximate)", min: [-500, -560, 412], max: [600, -255, 440] };
const HOME_BLOCK = [290, 20];
const STORE_KEY = "labdeck-lab-workspace";

let workspace = null;
let started = false;
let three = null;
const sim = {
  start: [0, 0, 0, 0, 0, 0],
  joints: [0, 0, 0, 0, 0, 0],
  program: null,
  time: 0,
  playing: false,
  speed: 1,
  lastBlock: null,
  block: { x: HOME_BLOCK[0], y: HOME_BLOCK[1], z: TABLE_Z, held: false, offset: [0, 0, 0] },
  suction: false,
};

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function isDark() {
  return css("--tank-is-dark") === "1";
}

// ---------- Blockly ----------
function treeFromDom(xml) {
  const kids = (el, name) => [...el.children].filter((c) => c.localName === name);
  const conv = (block) => {
    if (!block) return null;
    const node = { type: block.getAttribute("type"), id: block.getAttribute("id"), fields: {}, fieldOrder: [], values: {}, statements: {} };
    for (const c of block.children) {
      if (c.localName === "field") {
        node.fields[c.getAttribute("name")] = c.textContent;
        node.fieldOrder.push(c.getAttribute("name"));
      } else if (c.localName === "value" || c.localName === "statement") {
        const inner = kids(c, "block")[0] || kids(c, "shadow")[0];
        (c.localName === "value" ? node.values : node.statements)[c.getAttribute("name")] = conv(inner);
      } else if (c.localName === "next") node.next = conv(kids(c, "block")[0]);
      else if (c.localName === "mutation") node.mutationName = c.getAttribute("name");
    }
    if (node.type === "lab_unsupported") node.studioType = node.fields.TYPE;
    return node;
  };
  return kids(xml, "block").map(conv);
}

function knownTypes() {
  return new Set(Object.keys(B.Blocks));
}

function loadXml(xmlText, label) {
  const { dom, unknown } = window.StudioFile.importDom(xmlText, knownTypes());
  workspace.clear();
  B.Xml.domToWorkspace(dom, workspace);
  workspace.scrollCenter();
  log([{ level: "info", message: `Loaded ${label}.${unknown.length ? ` Kept but not simulated: ${unknown.join(", ")}.` : ""}` }]);
  resetSim();
}

function saveLocal() {
  try {
    localStorage.setItem(STORE_KEY, B.Xml.domToText(B.Xml.workspaceToDom(workspace)));
  } catch (_) {}
}

function applyBlocklyTheme() {
  if (workspace) workspace.setTheme(isDark() ? window.LabThemes.dark : window.LabThemes.light);
}

async function initBlockly() {
  workspace = B.inject("lab-blockly", {
    toolbox: window.LabToolbox,
    theme: isDark() ? window.LabThemes.dark : window.LabThemes.light,
    trashcan: true,
    zoom: { controls: true, wheel: true, startScale: 0.8 },
    grid: { spacing: 24, length: 2, colour: "rgba(77,95,128,.25)", snap: true },
    renderer: "zelos",
  });
  let saved = null;
  try {
    saved = localStorage.getItem(STORE_KEY);
  } catch (_) {}
  if (saved) loadXml(saved, "your last program");
  else {
    const res = await fetch("/assets/lab/example-vacuum.xml");
    if (res.ok) loadXml(await res.text(), "the example: a Studio vacuum loop");
  }
  workspace.addChangeListener((e) => {
    if (!e.isUiEvent) {
      saveLocal();
      if (sim.program && !sim.playing) sim.program = null;
    }
  });
}

// ---------- 3D scene ----------
async function initScene() {
  const host = $("lab-view");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  host.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 5, 20000);
  camera.up.set(0, 0, 1);
  camera.position.set(1150, 820, 720); // front-left, so the shelf (−Y) sits behind the arm
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(160, -90, 180);
  controls.enableDamping = true;
  controls.update();

  scene.add(new THREE.HemisphereLight(0xffffff, 0x334466, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(600, -900, 1400);
  scene.add(sun);

  // Table, grid and zones.
  const table = new THREE.Mesh(
    new THREE.PlaneGeometry(1800, 1400),
    new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, transparent: true, opacity: 0.9 }),
  );
  table.position.set(250, 0, TABLE_Z - 0.5);
  scene.add(table);
  const grid = new THREE.GridHelper(1800, 36, 0x4d5f80, 0x4d5f80);
  grid.rotation.x = Math.PI / 2;
  grid.position.set(250, 0, TABLE_Z);
  grid.material.transparent = true;
  grid.material.opacity = 0.25;
  scene.add(grid);

  const zones = new THREE.Group();
  scene.add(zones);
  try {
    const layout = await (await fetch("/api/workspace", { cache: "no-store" })).json();
    for (const [[x0, y0], [x1, y1]] of layout.regions || []) {
      const pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]].map(([x, y]) => new THREE.Vector3(x, y, TABLE_Z + 0.6));
      zones.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: 0x003087, dashSize: 10, gapSize: 8 })));
      zones.children.at(-1).computeLineDistances();
    }
  } catch (_) {}

  const shelfSize = SHELF.max.map((v, i) => v - SHELF.min[i]);
  const shelf = new THREE.Mesh(
    new THREE.BoxGeometry(...shelfSize),
    new THREE.MeshStandardMaterial({ color: 0xc6dae7, transparent: true, opacity: 0.22, roughness: 0.7, depthWrite: false }),
  );
  shelf.position.set(...SHELF.min.map((v, i) => v + shelfSize[i] / 2));
  shelf.add(new THREE.LineSegments(new THREE.EdgesGeometry(shelf.geometry), new THREE.LineBasicMaterial({ color: 0x4d5f80, transparent: true, opacity: 0.6 })));
  scene.add(shelf);

  // The block, with its green marker on top.
  const block = new THREE.Group();
  const cube = new THREE.Mesh(new THREE.BoxGeometry(BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE), new THREE.MeshStandardMaterial({ color: 0xc8a06a, roughness: 0.8 }));
  cube.position.z = BLOCK_SIZE / 2;
  const dot = new THREE.Mesh(new THREE.CircleGeometry(7, 24), new THREE.MeshStandardMaterial({ color: 0x2fbf4f }));
  dot.position.z = BLOCK_SIZE + 0.3;
  block.add(cube, dot);
  scene.add(block);

  // The robot from UFACTORY's meshes (meters → mm).
  const loader = new STLLoader();
  const names = ["link_base", "link1", "link2", "link3", "link4", "link5", "link6"];
  const material = new THREE.MeshStandardMaterial({ color: 0xf2f4f7, roughness: 0.45, metalness: 0.05 });
  const accent = new THREE.MeshStandardMaterial({ color: 0x9aa3ad, roughness: 0.5 });
  const links = names.map(() => {
    const g = new THREE.Group();
    g.matrixAutoUpdate = false;
    scene.add(g);
    return g;
  });
  await Promise.all(
    names.map(async (name, i) => {
      const geometry = await loader.loadAsync(`/assets/lite6/${name}.stl`);
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(geometry, i === 0 ? accent : material);
      mesh.scale.setScalar(1000);
      links[i].add(mesh);
    }),
  );
  // Suction cup on the flange (TCP offset is zero on this arm).
  const cup = new THREE.Mesh(new THREE.CylinderGeometry(9, 12, 18, 24), new THREE.MeshStandardMaterial({ color: 0x1d2433 }));
  cup.rotation.x = Math.PI / 2;
  cup.position.z = -9;
  links[6].add(cup);

  const pathLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.55 }));
  const trail = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ linewidth: 2 }));
  scene.add(pathLine, trail);

  three = { renderer, scene, camera, controls, links, block, cup, pathLine, trail, trailPts: [], host, table, grid, shelf };
  applySceneTheme();
  new ResizeObserver(resizeScene).observe(host);
  resizeScene();
}

function applySceneTheme() {
  if (!three) return;
  const dark = isDark();
  three.renderer.setClearColor(dark ? 0x000000 : 0xf7f9fc, 1);
  three.table.material.color.set(dark ? 0x0b1220 : 0xffffff);
  three.grid.material.color.set(dark ? 0x33466e : 0x9fb1d3);
  three.pathLine.material.color.set(css("--mark") || "#2b5fbf");
  three.trail.material.color.set(css("--coral") || "#cb333b");
}

function resizeScene() {
  if (!three) return;
  const { clientWidth: w, clientHeight: h } = three.host;
  three.renderer.setSize(w, h, false);
  three.camera.aspect = w / Math.max(1, h);
  three.camera.updateProjectionMatrix();
}

function setPose(q) {
  sim.joints = q.slice();
  const frames = K.linkFrames(q);
  frames.forEach((m, i) => {
    three.links[i].matrix.set(...m);
    three.links[i].matrixWorldNeedsUpdate = true;
  });
  const tool = K.fk(q);
  // Vacuum: grab the block when the cup touches its top with suction on.
  const b = sim.block;
  if (sim.suction && !b.held) {
    const top = [b.x, b.y, b.z + BLOCK_SIZE];
    if (Math.hypot(tool[0] - top[0], tool[1] - top[1]) < 15 && Math.abs(tool[2] - top[2]) < 6) {
      b.held = true;
      b.offset = [b.x - tool[0], b.y - tool[1], b.z - tool[2]];
      log([{ level: "info", message: "Block picked up." }], true);
    }
  }
  if (b.held && !sim.suction) {
    b.held = false;
    const overShelf = b.x > SHELF.min[0] && b.x < SHELF.max[0] && b.y > SHELF.min[1] && b.y < SHELF.max[1] && b.z >= SHELF.max[2] - 5;
    b.z = overShelf ? SHELF.max[2] : TABLE_Z;
    log([{ level: "info", message: overShelf ? "Block dropped onto the shelf." : "Block released onto the table." }], true);
  }
  if (b.held) {
    b.x = tool[0] + b.offset[0];
    b.y = tool[1] + b.offset[1];
    b.z = tool[2] + b.offset[2];
  }
  three.block.position.set(b.x, b.y, b.z);
  three.cup.material.color.set(sim.suction ? css("--coral") || "#cb333b" : 0x1d2433);
  readout(q, tool);
}

function readout(q, tool) {
  q.forEach((v, i) => {
    const slider = $(`jog-${i}`);
    if (slider && document.activeElement !== slider) slider.value = v.toFixed(1);
    const out = $(`jog-${i}-v`);
    if (out) out.textContent = `${v.toFixed(1)}°`;
  });
  $("lab-tcp").textContent = `Tool at x ${tool[0].toFixed(0)}, y ${tool[1].toFixed(0)}, z ${tool[2].toFixed(0)} mm · roll ${tool[3].toFixed(0)}°, pitch ${tool[4].toFixed(0)}°, yaw ${tool[5].toFixed(0)}°`;
}

// ---------- program ----------
function compileProgram() {
  for (const b of workspace.getAllBlocks(false)) b.setWarningText(null);
  const dom = B.Xml.workspaceToDom(workspace, false);
  const program = P.compile(treeFromDom(dom), {
    startJoints: sim.start,
    tableZ: TABLE_Z,
    obstacle: SHELF,
  });
  for (const f of program.findings) {
    const block = f.blockId && workspace.getBlockById(f.blockId);
    if (block && f.level !== "info") block.setWarningText(f.message);
  }
  // Whole planned tool path.
  const pts = [];
  for (const s of program.segments) for (const q of s.samples) {
    const t = K.fk(q);
    pts.push(new THREE.Vector3(t[0], t[1], t[2]));
  }
  three.pathLine.geometry.dispose();
  three.pathLine.geometry = new THREE.BufferGeometry().setFromPoints(pts);
  return program;
}

function log(items, append = false) {
  const list = $("lab-log");
  if (!append) list.replaceChildren();
  for (const f of items) {
    const li = document.createElement("li");
    li.className = f.level;
    li.textContent = f.message;
    if (f.blockId) {
      li.tabIndex = 0;
      li.addEventListener("click", () => workspace.getBlockById(f.blockId)?.select());
    }
    list.append(li);
  }
}

function resetSim() {
  sim.playing = false;
  sim.time = 0;
  sim.program = null;
  sim.suction = false;
  sim.block = { x: HOME_BLOCK[0], y: HOME_BLOCK[1], z: TABLE_Z, held: false, offset: [0, 0, 0] };
  three.trailPts = [];
  three.trail.geometry.dispose();
  three.trail.geometry = new THREE.BufferGeometry();
  workspace?.highlightBlock(null);
  setPose(sim.start);
  $("lab-run").textContent = "Run";
  $("lab-status").textContent = "Ready. Simulation only: nothing here moves the real arm.";
}

function run() {
  if (sim.playing) {
    sim.playing = false;
    $("lab-run").textContent = "Resume";
    return;
  }
  if (!sim.program) {
    resetSim();
    sim.program = compileProgram();
    const f = sim.program.findings;
    log(f.length ? f : [{ level: "info", message: "No problems found." }]);
    const errors = f.filter((x) => x.level === "error").length;
    $("lab-status").textContent = `${sim.program.segments.length} steps, ${sim.program.duration.toFixed(1)} s${errors ? ` · ${errors} problem${errors > 1 ? "s" : ""} to fix` : ""}`;
  }
  sim.playing = true;
  $("lab-run").textContent = "Pause";
}

function tick(dt) {
  if (!sim.playing || !sim.program) return;
  sim.time += dt * sim.speed;
  const segs = sim.program.segments;
  if (!segs.length || sim.time >= sim.program.duration) {
    if (segs.length) {
      const last = segs.at(-1);
      sim.suction = last.suction;
      setPose(last.samples.at(-1));
    }
    sim.playing = false;
    sim.program = null;
    workspace.highlightBlock(null);
    $("lab-run").textContent = "Run again";
    $("lab-status").textContent = "Finished.";
    return;
  }
  const seg = segs.find((s) => sim.time < s.start + s.duration) || segs.at(-1);
  sim.suction = seg.suction;
  const q = P.sample(seg, sim.time - seg.start);
  setPose(q);
  if (seg.blockId !== sim.lastBlock) {
    workspace.highlightBlock(seg.blockId);
    sim.lastBlock = seg.blockId;
  }
  const t = K.fk(q);
  three.trailPts.push(new THREE.Vector3(t[0], t[1], t[2]));
  if (three.trailPts.length > 4000) three.trailPts.shift();
  three.trail.geometry.dispose();
  three.trail.geometry = new THREE.BufferGeometry().setFromPoints(three.trailPts);
}

// ---------- controls ----------
function buildJog() {
  const box = $("lab-jog");
  K.LIMITS.forEach(([lo, hi], i) => {
    const row = document.createElement("label");
    row.className = "jog";
    const name = document.createElement("span");
    name.textContent = `J${i + 1}`;
    const input = document.createElement("input");
    Object.assign(input, { type: "range", min: Math.max(lo, -180), max: Math.min(hi, 180), step: 0.5, id: `jog-${i}`, value: 0 });
    if (i === 3 || i === 5) Object.assign(input, { min: -360, max: 360 });
    const out = document.createElement("b");
    out.id = `jog-${i}-v`;
    input.addEventListener("input", () => {
      if (sim.playing) return;
      const q = sim.joints.slice();
      q[i] = Number(input.value);
      sim.start = q;
      sim.program = null;
      setPose(q);
    });
    row.append(name, input, out);
    box.append(row);
  });
}

function addMoveFromPose() {
  const block = workspace.newBlock("move_joints");
  ["i", "j", "k", "l", "m", "n"].forEach((f, i) => block.setFieldValue(Math.round(sim.joints[i] * 10) / 10, f));
  block.initSvg();
  block.render();
  // Append to the end of the first stack, or start one.
  const top = workspace.getTopBlocks(true).find((b) => b.nextConnection);
  if (top) {
    let last = top;
    while (last.getNextBlock()) last = last.getNextBlock();
    last.nextConnection.connect(block.previousConnection);
  } else block.moveBy(40, 40);
  block.select();
  log([{ level: "info", message: "Added a move to the sim's current pose." }]);
}

async function syncFromArm() {
  try {
    const data = await (await fetch("/api/status", { cache: "no-store" })).json();
    const q = data.robot?.fresh ? data.robot.values?.joints?.slice(0, 6) : null;
    if (!q) throw new Error("No fresh arm telemetry");
    sim.start = q;
    resetSim();
    log([{ level: "info", message: "Simulator now starts from the real arm's current pose." }]);
  } catch (error) {
    log([{ level: "error", message: `${error.message}. The sim keeps its own pose.` }]);
  }
}

async function importProject(file) {
  try {
    const { xml, deviceType } = await window.StudioFile.readProject(file);
    if (deviceType && deviceType !== "lite6") log([{ level: "warning", message: `This project was made for a ${deviceType}, not a Lite 6.` }]);
    loadXml(xml, file.name);
  } catch (error) {
    log([{ level: "error", message: `Couldn't open ${file.name}: ${error.message}` }]);
  }
}

async function exportProject() {
  const xml = window.StudioFile.exportXml(B.Xml.workspaceToDom(workspace, false));
  const blob = await window.StudioFile.writeProject(xml);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `lab-program-${new Date().toISOString().slice(0, 10)}.tar.gz`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  log([{ level: "info", message: "Exported in Studio's project format (.tar.gz)." }]);
}

function bindControls() {
  $("lab-run").addEventListener("click", run);
  $("lab-reset").addEventListener("click", resetSim);
  $("lab-speed").addEventListener("change", (e) => (sim.speed = Number(e.target.value)));
  $("lab-add-pose").addEventListener("click", addMoveFromPose);
  $("lab-sync").addEventListener("click", syncFromArm);
  $("lab-home").addEventListener("click", () => {
    sim.start = [0, 0, 0, 0, 0, 0];
    resetSim();
  });
  $("lab-export").addEventListener("click", exportProject);
  $("lab-import").addEventListener("click", () => $("lab-file").click());
  $("lab-file").addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) importProject(file);
    e.target.value = "";
  });
}

async function start() {
  if (started) {
    B.svgResize(workspace);
    resizeScene();
    return;
  }
  started = true;
  buildJog();
  await initScene();
  await initBlockly();
  bindControls();
  try {
    const geo = await (await fetch("/api/lab-kinematics", { cache: "no-store" })).json();
    if (geo.joints && K.setGeometry(geo.joints))
      $("lab-calibration").textContent = `Kinematics calibrated to this arm (±${geo.fit.fitted_max_position_mm.toFixed(1)} mm).`;
  } catch (_) {}
  resetSim();
  let last = performance.now();
  const frame = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (!$("lab").hidden) {
      tick(dt);
      three.controls.update();
      three.renderer.render(three.scene, three.camera);
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

// Start when the Lab page is first opened (Blockly needs a visible container).
for (const button of document.querySelectorAll('[data-page="lab"]'))
  button.addEventListener("click", () => requestAnimationFrame(() => start()));
window.addEventListener("labdeck:theme", () => setTimeout(() => (applyBlocklyTheme(), applySceneTheme()), 0));
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => setTimeout(() => (applyBlocklyTheme(), applySceneTheme()), 0));
// #lab opens this tab; #lab-autorun also runs the loaded program (handy for demos).
if (location.hash.startsWith("#lab")) {
  document.querySelector('[data-page="lab"]')?.click();
  if (location.hash === "#lab-autorun") {
    const wait = () => (workspace && three ? setTimeout(run, 300) : setTimeout(wait, 200));
    wait();
  }
}
