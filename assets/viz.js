/* Display-only readings and the theme toggle.
 * Reads the "labdeck:status" snapshots app.js already fetches; sends nothing
 * to the robot. Marks use --mark (one series per chart, so one hue).
 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (name, attrs = {}) => {
    const el = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  };

  // ---------- theme: auto → light → dark (per-browser convenience) ----------
  const themes = ["auto", "light", "dark"];
  const root = document.documentElement;
  const toggle = $("theme-toggle");
  const current = () => root.dataset.theme || "auto";
  const show = () => (toggle.textContent = "Theme: " + current());
  toggle.addEventListener("click", () => {
    const next = themes[(themes.indexOf(current()) + 1) % themes.length];
    if (next === "auto") delete root.dataset.theme;
    else root.dataset.theme = next;
    try {
      if (next === "auto") localStorage.removeItem("labdeck-theme");
      else localStorage.setItem("labdeck-theme", next);
    } catch (_) {}
    show();
    window.dispatchEvent(new Event("labdeck:theme"));
  });
  show();

  // ---------- joint bars: centered at 0°, ±180° full scale ----------
  function jointBars(joints) {
    const box = $("joint-bars");
    box.replaceChildren();
    if (!Array.isArray(joints)) {
      box.textContent = "Waiting for telemetry.";
      return;
    }
    joints.slice(0, 6).forEach((value, i) => {
      const row = document.createElement("div");
      row.className = "joint";
      const name = document.createElement("span");
      name.textContent = `J${i + 1}`;
      const track = document.createElement("span");
      track.className = "track";
      const fill = document.createElement("span");
      fill.className = "fill";
      const share = Math.min(1, Math.abs(value) / 180) * 50;
      fill.style.width = `${share}%`;
      fill.style.left = value < 0 ? `${50 - share}%` : "50%";
      fill.classList.toggle("neg", value < 0);
      track.title = `J${i + 1}: ${value.toFixed(1)}°`;
      track.append(fill);
      const val = document.createElement("b");
      val.textContent = `${value.toFixed(1)}°`;
      row.append(name, track, val);
      box.append(row);
    });
  }

  // ---------- sparklines: one series each, never a shared axis ----------
  const history = { fps: [], ms: [] };
  const KEEP = 90;
  function spark(id, values, digits) {
    const svg = $(id);
    const valueEl = $(id + "-value");
    svg.replaceChildren();
    if (!values.length) {
      valueEl.textContent = "—";
      return;
    }
    const W = 240, H = 48, pad = 4;
    const max = Math.max(...values) * 1.15 || 1;
    const offset = KEEP - values.length;
    const x = (i) => pad + ((i + offset) / (KEEP - 1)) * (W - 2 * pad);
    const y = (v) => H - pad - (v / max) * (H - 2 * pad);
    const pts = values.map((v, i) => [x(i), y(v)]);
    const line = pts.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
    svg.append(
      svgEl("line", { class: "base", x1: pad, y1: H - pad, x2: W - pad, y2: H - pad }),
      svgEl("polygon", { class: "area", points: `${pts[0][0]},${H - pad} ${line} ${pts.at(-1)[0]},${H - pad}` }),
      svgEl("polyline", { class: "line", points: line }),
      svgEl("circle", { class: "last", cx: pts.at(-1)[0], cy: pts.at(-1)[1], r: 4 }),
    );
    const latest = () => (valueEl.textContent = values.at(-1).toFixed(digits));
    latest();
    svg.onpointermove = (event) => {
      const box = svg.getBoundingClientRect();
      const i = Math.round(((event.clientX - box.left) / box.width) * (KEEP - 1)) - offset;
      if (i >= 0 && i < values.length) valueEl.textContent = values[i].toFixed(digits);
    };
    svg.onpointerleave = latest;
  }

  // ---------- where the last cycle spent its time ----------
  let lastKey = "";
  function phaseBar(job) {
    const seconds = job?.phase_seconds;
    const key = JSON.stringify(seconds || null);
    if (key === lastKey) return;
    lastKey = key;
    const bar = $("phase-bar");
    let labels = bar.nextElementSibling;
    if (!labels?.classList.contains("phase-labels")) {
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
      empty.textContent = "Run a cycle to see its timing.";
      bar.append(empty);
      return;
    }
    const total = entries.reduce((sum, [, s]) => sum + s, 0);
    for (const [phase, s] of entries) {
      const seg = document.createElement("span");
      seg.className = "seg";
      seg.style.flexGrow = String(s);
      seg.title = `${phase}: ${s.toFixed(1)} s`;
      bar.append(seg);
      const item = document.createElement("span");
      const name = document.createElement("b");
      name.textContent = phase;
      item.append(name, ` ${s.toFixed(1)} s`);
      labels.append(item);
    }
    const sum = document.createElement("span");
    sum.className = "total";
    sum.textContent = `${total.toFixed(1)} s in all`;
    labels.append(sum);
  }

  window.addEventListener("labdeck:status", (event) => {
    const data = event.detail;
    if (!data) {
      jointBars(null);
      return;
    }
    const robot = data.robot || {};
    jointBars(robot.fresh ? robot.values?.joints : null);
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
