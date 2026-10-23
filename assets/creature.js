/* Light trap: ASCII moths drawn to whatever the camera is detecting.
 * Display-only. The "light" is the first detection's centroid (green block or
 * palm), mapped from sensor pixels into this canvas the same way the camera
 * view is shown (rotated 180°). When the arm moves (a job, follow session,
 * start-pose move, or a joint change between snapshots) the moths scatter.
 *
 * Rendering follows the cell-grid idea of ascii-sharks: everything is a glyph
 * on a monospace grid, and a decaying "wake" field lights cells where moths
 * have flown. Our own code; no third-party source is used.
 */
"use strict";
(() => {
  const canvas = document.getElementById("trap");
  const caption = document.getElementById("trap-caption");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const CELL_W = 9;
  const CELL_H = 14;
  const WINGS = [
    ["\\", "/"],
    ["-", "-"],
    ["/", "\\"],
    ["-", "-"],
  ];
  const WAKE_GLYPHS = " .·:∙*";

  let cols = 0;
  let rows = 0;
  let wake = new Float32Array(0);
  let colors = {};
  const moths = [];
  const light = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5, live: false, label: "idle" };
  let agitation = 0;
  let lastJoints = null;
  let visible = true;

  function readColors() {
    const css = getComputedStyle(document.documentElement);
    const get = (name) => css.getPropertyValue(name).trim();
    colors = {
      bg: get("--panel"),
      ink: get("--ink"),
      muted: get("--muted"),
      wake: get("--hot"),
      lamp: get("--warn"),
      flee: get("--hot-2"),
    };
  }

  function resize() {
    const box = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.max(8, Math.floor(box.width / CELL_W));
    rows = Math.max(4, Math.floor(box.height / CELL_H));
    wake = new Float32Array(cols * rows);
  }

  function spawn() {
    moths.length = 0;
    for (let i = 0; i < 26; i++) {
      moths.push({
        x: Math.random(),
        y: Math.random(),
        vx: (Math.random() - 0.5) * 0.2,
        vy: (Math.random() - 0.5) * 0.2,
        phase: Math.random() * 4,
        orbit: Math.random() < 0.5 ? 1 : -1,
        reach: 0.08 + Math.random() * 0.16,
      });
    }
  }

  function step(dt, t) {
    // An idle light wanders on a slow Lissajous path.
    if (!light.live) {
      light.tx = 0.5 + 0.32 * Math.sin(t * 0.00011);
      light.ty = 0.5 + 0.28 * Math.sin(t * 0.00017 + 1.3);
    }
    light.x += (light.tx - light.x) * Math.min(1, dt * 3);
    light.y += (light.ty - light.y) * Math.min(1, dt * 3);
    agitation = Math.max(0, agitation - dt * 0.35);
    const aspect = cols / Math.max(1, rows) / 1.6;
    for (const m of moths) {
      const dx = (light.x - m.x) * aspect;
      const dy = light.y - m.y;
      const d = Math.hypot(dx, dy) + 1e-4;
      // Pull toward a personal orbit radius, plus a tangential swirl.
      const pull = (d - m.reach) * (light.live ? 2.6 : 1.2);
      let ax = (dx / d) * pull - (dy / d) * m.orbit * 0.9;
      let ay = (dy / d) * pull + (dx / d) * m.orbit * 0.9;
      // Arm motion: flee the light and jitter.
      if (agitation > 0.05) {
        ax -= (dx / d) * 4 * agitation;
        ay -= (dy / d) * 4 * agitation;
      }
      const jitter = 0.9 + agitation * 3;
      ax += (Math.random() - 0.5) * jitter;
      ay += (Math.random() - 0.5) * jitter;
      m.vx = (m.vx + (ax / aspect) * dt) * 0.96;
      m.vy = (m.vy + ay * dt) * 0.96;
      const speed = Math.hypot(m.vx, m.vy);
      const max = 0.32 + agitation * 0.5;
      if (speed > max) {
        m.vx *= max / speed;
        m.vy *= max / speed;
      }
      m.x += m.vx * dt;
      m.y += m.vy * dt;
      if (m.x < 0.02 || m.x > 0.98) m.vx *= -1;
      if (m.y < 0.04 || m.y > 0.96) m.vy *= -1;
      m.x = Math.min(0.98, Math.max(0.02, m.x));
      m.y = Math.min(0.96, Math.max(0.04, m.y));
      m.phase += dt * (8 + speed * 30);
      const c = Math.floor(m.x * cols);
      const r = Math.floor(m.y * rows);
      wake[r * cols + c] = Math.min(1, wake[r * cols + c] + 0.5);
    }
    for (let i = 0; i < wake.length; i++) wake[i] *= 0.94;
  }

  function draw(t) {
    const w = cols * CELL_W;
    const h = rows * CELL_H;
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = `${CELL_H - 2}px "Space Mono", ui-monospace, monospace`;
    ctx.textBaseline = "top";
    // Wake field.
    ctx.fillStyle = colors.wake;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = wake[r * cols + c];
        if (v < 0.06) continue;
        ctx.globalAlpha = Math.min(0.9, v);
        const g = WAKE_GLYPHS[Math.min(WAKE_GLYPHS.length - 1, Math.floor(v * WAKE_GLYPHS.length))];
        ctx.fillText(g, c * CELL_W, r * CELL_H);
      }
    }
    // The light: a lamp glyph with a pulsing dotted halo.
    const lx = light.x * w;
    const ly = light.y * h;
    ctx.fillStyle = colors.lamp;
    const pulse = 0.5 + 0.5 * Math.sin(t * 0.004);
    const radius = (light.live ? 2.2 : 1.5) + pulse * 0.8;
    for (let a = 0; a < 16; a++) {
      const ang = (a / 16) * Math.PI * 2 + t * 0.0004;
      ctx.globalAlpha = light.live ? 0.55 : 0.25;
      ctx.fillText(".", lx + Math.cos(ang) * radius * CELL_W * 1.6, ly + Math.sin(ang) * radius * CELL_H);
    }
    ctx.globalAlpha = light.live ? 1 : 0.5;
    ctx.fillText(light.live ? "✶" : "*", lx - CELL_W / 2, ly - CELL_H / 2);
    // Moths: wing / body / wing, flapping with their speed.
    ctx.fillStyle = agitation > 0.2 ? colors.flee : colors.ink;
    for (const m of moths) {
      const wings = WINGS[Math.floor(m.phase) % WINGS.length];
      const x = Math.floor(m.x * cols) * CELL_W;
      const y = Math.floor(m.y * rows) * CELL_H;
      ctx.globalAlpha = 0.95;
      ctx.fillText(wings[0] + "o" + wings[1], x - CELL_W, y);
    }
    ctx.globalAlpha = 1;
  }

  let last = performance.now();
  let accum = 0;
  let lastDraw = 0;
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    accum += dt;
    // Reduced motion: a slow 2 fps drift instead of continuous flight.
    if (visible && (!reduced || accum > 0.5)) {
      step(reduced ? accum : dt, now);
      draw(now);
      lastDraw = now;
      accum = 0;
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener("labdeck:status", (event) => {
    const data = event.detail;
    if (!data) {
      light.live = false;
      caption.textContent = "link lost";
      return;
    }
    const v = data.vision || {};
    const target = v.fresh && v.detections?.length ? v.detections[0] : null;
    const center =
      target?.center ||
      (target?.bbox ? [target.bbox[0] + target.bbox[2] / 2, target.bbox[1] + target.bbox[3] / 2] : null);
    if (center) {
      const [W, H] = v.resolution || [640, 400];
      // Same 180° display rotation as the camera view.
      light.tx = (W - 1 - center[0]) / W;
      light.ty = (H - 1 - center[1]) / H;
      light.live = true;
    } else {
      light.live = false;
    }
    const joints = data.robot?.fresh ? data.robot.values?.joints : null;
    let moved = false;
    if (Array.isArray(joints) && Array.isArray(lastJoints)) {
      moved = joints.slice(0, 6).some((a, i) => Math.abs(a - lastJoints[i]) > 0.5);
    }
    lastJoints = Array.isArray(joints) ? joints.slice(0, 6) : null;
    const busy =
      data.job?.state === "running" || data.follow?.state === "running" || data.transfer?.state === "running";
    if (moved || busy) agitation = Math.min(1, agitation + 0.6);
    // If animation frames are throttled, still show a current frame.
    const now = performance.now();
    if (now - lastDraw > 500) {
      step(0.05, now);
      draw(now);
      lastDraw = now;
    }
    caption.textContent =
      agitation > 0.2
        ? "arm moving · scatter"
        : center
          ? `drawn to ${target.gesture ? "palm" : target.label || "target"}`
          : "no light · wandering";
  });

  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver((entries) => {
    visible = entries.some((e) => e.isIntersecting) && !document.hidden;
  }).observe(canvas);
  document.addEventListener("visibilitychange", () => (visible = !document.hidden));
  window.addEventListener("labdeck:theme", () => setTimeout(readColors, 0));
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => setTimeout(readColors, 0));
  readColors();
  resize();
  spawn();
  requestAnimationFrame(frame);
})();
