/* Display-only data views and the theme toggle.
 * Reads the "labdeck:status" snapshots that app.js already fetches; sends
 * nothing to the robot. Chart marks use CSS tokens --mark-a / --mark-b, a
 * categorical pair validated for both themes (dataviz validate_palette.js:
 * light #1f35d6/#c2127f on #eceee9, dark #14a3b4/#a8389c on #0b0e12).
 * Every zone is also direct-labeled, so identity never rests on color alone.
 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (name, attrs = {}, text) => {
    const el = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text != null) el.textContent = text;
    return el;
  };

  // ---------- theme: auto → light → dark (per-browser convenience) ----------
  const themes = ["auto", "light", "dark"];
  const root = document.documentElement;
  const toggle = $("theme-toggle");
  const currentTheme = () => root.dataset.theme || "auto";
  const showTheme = () => (toggle.textContent = "theme: " + currentTheme());
  toggle.addEventListener("click", () => {
    const next = themes[(themes.indexOf(currentTheme()) + 1) % themes.length];
    if (next === "auto") delete root.dataset.theme;
    else root.dataset.theme = next;
    try {
      if (next === "auto") localStorage.removeItem("labdeck-theme");
      else localStorage.setItem("labdeck-theme", next);
    } catch (_) {}
    showTheme();
    window.dispatchEvent(new Event("labdeck:theme"));
  });
  showTheme();

  // ---------- joint bars: ASCII, centered at 0°, ±180° full scale ----------
  const HALF = 12;
  function jointBars(joints) {
    const pre = $("joint-bars");
    pre.replaceChildren();
    if (!Array.isArray(joints)) {
      pre.textContent = "no fresh telemetry";
      return;
    }
    joints.slice(0, 6).forEach((value, i) => {
      const n = Math.min(HALF, Math.round((Math.abs(value) / 180) * HALF));
      const left = value < 0 ? "·".repeat(HALF - n) + "■".repeat(n) : "·".repeat(HALF);
      const right = value > 0 ? "■".repeat(n) + "·".repeat(HALF - n) : "·".repeat(HALF);
      const bar = document.createElement("span");
      bar.className = "bar";
      bar.textContent = left + "┃" + right;
      const val = document.createElement("span");
      val.className = "val";
      val.textContent = (value >= 0 ? " " : "") + value.toFixed(1).padStart(6) + "°";
      pre.append(`J${i + 1} [`, bar, "] ", val, "\n");
    });
  }

  // ---------- top-down workspace map (robot mm; X forward=up, Y left=left) ----------
  const map = $("ws-map");
  let layout = { regions: [], shelf_drop_xy: null };
  const trail = [];
  const toSvg = ([x, y]) => [-y, -x];
  function drawMap(pose) {
    map.replaceChildren();
    map.append(
      svgEl("line", { class: "axis", x1: -450, y1: 0, x2: 450, y2: 0 }),
      svgEl("line", { class: "axis", x1: 0, y1: 60, x2: 0, y2: -450 }),
      svgEl("circle", { class: "reach", cx: 0, cy: 0, r: 440 }),
      svgEl("text", { x: 10, y: -420 }, "+X forward"),
    );
    for (const [[x0, y0], [x1, y1]] of layout.regions) {
      const zone = svgEl("rect", {
        class: "zone",
        x: -y1,
        y: -x1,
        width: y1 - y0,
        height: x1 - x0,
      });
      zone.append(svgEl("title", {}, `pickup zone · X ${x0}–${x1}, Y ${y0}–${y1} mm`));
      map.append(zone, svgEl("text", { x: -y1 + 6, y: -x1 - 10 }, "pickup zone"));
    }
    if (layout.shelf_drop_xy) {
      const [sx, sy] = toSvg(layout.shelf_drop_xy);
      const shelf = svgEl("rect", { class: "shelf", x: sx - 14, y: sy - 14, width: 28, height: 28 });
      shelf.append(svgEl("title", {}, `shelf drop · X ${layout.shelf_drop_xy.map((v) => v.toFixed(0)).join(", Y ")} mm`));
      map.append(shelf, svgEl("text", { x: sx - 60, y: sy + 46 }, "shelf drop"));
    }
    map.append(svgEl("circle", { class: "base", cx: 0, cy: 0, r: 22 }));
    if (trail.length > 1)
      map.append(svgEl("polyline", { class: "trail", points: trail.map((p) => toSvg(p).join(",")).join(" ") }));
    if (Array.isArray(pose)) {
      const [tx, ty] = toSvg(pose);
      const tool = svgEl("circle", { class: "tool", cx: tx, cy: ty, r: 12 });
      tool.append(svgEl("title", {}, `tool · X ${pose[0].toFixed(0)}, Y ${pose[1].toFixed(0)}, Z ${pose[2].toFixed(0)} mm`));
      map.append(tool, svgEl("text", { x: tx + 18, y: ty - 14 }, `tool z${pose[2].toFixed(0)}`));
    }
  }
  async function loadLayout() {
    try {
      const response = await fetch("/api/workspace", { cache: "no-store" });
      if (response.ok) layout = await response.json();
    } catch (_) {}
    drawMap(null);
  }
  loadLayout();

  // ---------- sparklines: one series each, never a shared axis ----------
  const history = { fps: [], ms: [] };
  const KEEP = 90;
  function spark(id, values, digits) {
    const svg = $(id);
    svg.replaceChildren();
    const valueEl = $(id + "-value");
    if (!values.length) {
      valueEl.textContent = "—";
      return;
    }
    const W = 240, H = 48, pad = 4;
    const max = Math.max(...values) * 1.15 || 1;
    const x = (i) => pad + (i / Math.max(1, KEEP - 1)) * (W - 2 * pad);
    const y = (v) => H - pad - (v / max) * (H - 2 * pad);
    const offset = KEEP - values.length;
    const pts = values.map((v, i) => [x(i + offset), y(v)]);
    const line = pts.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
    svg.append(
      svgEl("line", { class: "base", x1: pad, y1: H - pad, x2: W - pad, y2: H - pad }),
      svgEl("polygon", { class: "area", points: `${pts[0][0]},${H - pad} ${line} ${pts.at(-1)[0]},${H - pad}` }),
      svgEl("polyline", { class: "line", points: line }),
      svgEl("circle", { class: "last", cx: pts.at(-1)[0], cy: pts.at(-1)[1], r: 4 }),
    );
    valueEl.textContent = values.at(-1).toFixed(digits);
    // Hover: read the nearest sample into the header value.
    svg.onpointermove = (event) => {
      const box = svg.getBoundingClientRect();
      const i = Math.round(((event.clientX - box.left) / box.width) * (KEEP - 1)) - offset;
      if (i >= 0 && i < values.length) valueEl.textContent = values[i].toFixed(digits);
    };
    svg.onpointerleave = () => (valueEl.textContent = values.at(-1).toFixed(digits));
  }

  // ---------- phase timeline of the last finished cycle ----------
  let lastPhaseKey = "";
  function phaseBar(job) {
    const seconds = job?.phase_seconds;
    const key = JSON.stringify(seconds || null) + job?.state;
    if (key === lastPhaseKey) return;
    lastPhaseKey = key;
    const bar = $("phase-bar");
    let labels = bar.nextElementSibling;
    if (!labels || !labels.classList.contains("phase-labels")) {
      labels = document.createElement("div");
      labels.className = "phase-labels";
      bar.after(labels);
    }
    bar.replaceChildren();
    labels.replaceChildren();
    const entries = Object.entries(seconds || {}).filter(([, s]) => s > 0.05);
    if (!entries.length) {
      const empty = document.createElement("span");
      empty.className = "empty";
      empty.textContent = "no completed cycle yet";
      bar.append(empty);
      return;
    }
    const total = entries.reduce((sum, [, s]) => sum + s, 0);
    for (const [phase, s] of entries) {
      const seg = document.createElement("span");
      seg.className = "phase-seg";
      seg.style.flexGrow = String(s);
      seg.title = `${phase} · ${s.toFixed(1)} s`;
      bar.append(seg);
      const label = document.createElement("span");
      const name = document.createElement("b");
      name.textContent = phase;
      label.append(name, ` ${s.toFixed(1)}s`);
      labels.append(label);
    }
    const sum = document.createElement("span");
    sum.textContent = `· total ${total.toFixed(1)} s`;
    labels.append(sum);
  }

  // ---------- ticker ----------
  function ticker(data) {
    const t = $("ticker");
    if (!data) {
      t.textContent = "/// link lost · reconnecting /// telemetry frozen ///";
      return;
    }
    const v = data.robot?.values || {};
    const j = Array.isArray(v.joints) ? v.joints.slice(0, 6).map((a, i) => `J${i + 1} ${a.toFixed(1)}°`).join("  ") : "joints —";
    const p = Array.isArray(v.pose) ? `xyz ${v.pose.slice(0, 3).map((a) => a.toFixed(0)).join("/")} mm` : "xyz —";
    t.textContent = [
      `state ${v.state ?? "—"}`,
      j,
      p,
      `fps ${data.vision?.fresh ? data.vision.fps.toFixed(1) : "—"}`,
      `job ${data.job?.state ?? "—"}`,
      `follow ${data.follow?.state ?? "—"}`,
      "the physical e-stop is the only immediate stop",
    ].join("   ///   ");
  }

  window.addEventListener("labdeck:status", (event) => {
    const data = event.detail;
    ticker(data);
    if (!data) {
      jointBars(null);
      return;
    }
    const robot = data.robot || {};
    const values = robot.fresh ? robot.values : {};
    jointBars(values.joints);
    if (Array.isArray(values.pose)) {
      const last = trail.at(-1);
      if (!last || Math.hypot(last[0] - values.pose[0], last[1] - values.pose[1]) > 1) {
        trail.push(values.pose.slice(0, 2));
        if (trail.length > 60) trail.shift();
      }
    }
    drawMap(values.pose);
    if (data.vision?.fresh) {
      history.fps.push(data.vision.fps);
      history.ms.push(data.vision.processing_ms);
      for (const k of ["fps", "ms"]) if (history[k].length > KEEP) history[k].shift();
    }
    spark("spark-fps", history.fps, 1);
    spark("spark-ms", history.ms, 1);
    phaseBar(data.job);
  });
})();
