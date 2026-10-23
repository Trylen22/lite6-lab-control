/* The tank: the robot workspace seen from above, drawn as an ASCII aquarium.
 *
 * It is a real map, to scale (robot millimeters; +X forward is up, +Y is
 * left): the arm base sits at the bottom, the kelp bed is the validated
 * pickup zone, the ledge is the shelf drop, and the dotted arc is reach.
 *   shark  = the arm's tool position (telemetry, every 3 s). It swims to the
 *            reported point and circles there; when the arm moves, it chases.
 *   fish   = decoration with a job: they swarm the detected block (estimated
 *            with the same tabletop calibration pickup uses) and scatter from
 *            the shark.
 * Display-only: nothing here is sent to the robot.
 *
 * Technique (after stackedlol/ascii-sharks, our own code): everything is a
 * glyph on a monospace grid. The shark is a top-down silhouette — a spine
 * that follows the head, a body-width profile, fins and a forked tail —
 * rasterized cell by cell and shaded by a light from the upper left, with a
 * travelling body wave so it actually swims.
 */
"use strict";
(() => {
  const canvas = document.getElementById("tank");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const captionEl = document.getElementById("tank-caption");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const MONO = '"DejaVu Sans Mono", "Menlo", "Consolas", ui-monospace, monospace';
  const UI = '"Avenir Next", "Avenir", "Nunito Sans", system-ui, sans-serif';
  const FONT_PX = 10;
  const CELL_H = 10;
  let CELL_W = 8;

  // ---------- world ↔ screen ----------
  const view = { w: 0, h: 0, cols: 0, rows: 0, scale: 0.6, baseX: 0, baseY: 0 };
  const toPx = (xMm, yMm) => [view.baseX - yMm * view.scale, view.baseY - xMm * view.scale];

  // ---------- inputs ----------
  const state = {
    layout: { regions: [], shelf_drop_xy: null },
    calib: null,
    tool: null, // [x, y, z] mm
    food: null, // [x, y] mm
    busy: false,
    fresh: false,
  };

  // ---------- palette (read from CSS tokens; validated in style.css) ----------
  let pal = {};
  function readPalette() {
    const css = getComputedStyle(document.documentElement);
    const get = (n) => css.getPropertyValue(n).trim();
    pal = {
      deep: get("--tank-deep"),
      shallow: get("--tank-shallow"),
      body: get("--tank-shark"),
      fish: get("--tank-fish"),
      food: get("--tank-food"),
      sand: get("--tank-sand"),
      water: get("--tank-water"),
      label: get("--tank-label"),
      dark: get("--tank-is-dark") === "1",
    };
  }

  // ---------- cheap value noise for the water ----------
  function hash(x, y) {
    let h = (x * 374761393 + y * 668265263) | 0;
    h = (h ^ (h >>> 13)) * 1274126177;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  }
  function noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }

  // ---------- shark ----------
  const N = 20;
  const shark = {
    nodes: [],
    heading: 0,
    speed: 40,
    phase: 0,
    length: 200,
    orbit: 1,
  };
  function placeShark(x, y) {
    shark.nodes = [];
    const seg = shark.length / (N - 1);
    for (let i = 0; i < N; i++)
      shark.nodes.push([x - Math.cos(shark.heading) * seg * i, y - Math.sin(shark.heading) * seg * i]);
  }

  // Body half-width along the spine (fraction of length): blunt snout,
  // widest just behind the gills, long taper into the tail stock.
  function halfWidth(s) {
    if (s < 0.14) return 0.105 * Math.pow(Math.sin(((s / 0.14) * Math.PI) / 2), 0.75);
    if (s < 0.32) return 0.105 + 0.012 * Math.sin(((s - 0.14) / 0.18) * Math.PI);
    if (s < 0.86) return 0.016 + 0.089 * Math.pow(1 - (s - 0.32) / 0.54, 1.35);
    return 0.016;
  }
  // Pectoral fin, swept back: u is the distance past the body edge (in
  // lengths). The leading edge runs back faster than the trailing edge,
  // so the two meet at a tip behind the fin root.
  function inPectoral(s, u) {
    if (u <= 0 || u > 0.22) return false;
    return s > 0.24 + 1.05 * u && s < 0.37 + 0.45 * u;
  }
  // Small pelvic fins near the back.
  function pelvic(s) {
    if (s < 0.6 || s > 0.7) return 0;
    return 0.05 * Math.sin(((s - 0.6) / 0.1) * Math.PI);
  }

  function steerShark(dt, t) {
    const head = shark.nodes[0];
    let target;
    if (state.tool) target = toPx(state.tool[0], state.tool[1]);
    else target = [view.baseX + Math.sin(t * 0.00009) * view.w * 0.3, view.baseY - view.h * 0.55];
    const dx = target[0] - head[0], dy = target[1] - head[1];
    const dist = Math.hypot(dx, dy);
    let desired, want;
    const ring = shark.length * 0.42;
    if (dist > ring * 1.6) {
      desired = Math.atan2(dy, dx);
      want = Math.min(state.busy ? 170 : 110, 40 + dist * 0.8);
    } else {
      // Patrol a wide circle around the tool point.
      const lean = Math.max(-1, Math.min(1, (dist - ring) / ring));
      desired = Math.atan2(dy, dx) - shark.orbit * (Math.PI / 2) * (1 - lean);
      want = 46;
    }
    let turn = Math.atan2(Math.sin(desired - shark.heading), Math.cos(desired - shark.heading));
    const maxTurn = 1.6 * dt;
    turn = Math.max(-maxTurn, Math.min(maxTurn, turn));
    shark.heading += turn;
    shark.speed += (want - shark.speed) * Math.min(1, dt * 1.5);
    head[0] += Math.cos(shark.heading) * shark.speed * dt;
    head[1] += Math.sin(shark.heading) * shark.speed * dt;
    const seg = shark.length / (N - 1);
    for (let i = 1; i < N; i++) {
      const p = shark.nodes[i], q = shark.nodes[i - 1];
      const ex = p[0] - q[0], ey = p[1] - q[1];
      const len = Math.hypot(ex, ey) || 1;
      p[0] = q[0] + (ex / len) * seg;
      p[1] = q[1] + (ey / len) * seg;
    }
    shark.phase += dt * (3.2 + shark.speed * 0.035);
  }

  // Spine with the swimming wave applied (amplitude grows toward the tail).
  function wavySpine() {
    const pts = [];
    const amp = shark.length * 0.055 * (0.55 + Math.min(1, shark.speed / 120) * 0.6);
    for (let i = 0; i < N; i++) {
      const a = shark.nodes[Math.max(0, i - 1)], b = shark.nodes[Math.min(N - 1, i + 1)];
      const tx = a[0] - b[0], ty = a[1] - b[1];
      const tl = Math.hypot(tx, ty) || 1;
      const k = i / (N - 1);
      const off = amp * Math.pow(k, 1.4) * Math.sin(shark.phase - i * 0.55);
      pts.push([shark.nodes[i][0] + (-ty / tl) * off, shark.nodes[i][1] + (tx / tl) * off]);
    }
    return pts;
  }

  const RAMP = ".:-=+*#%@";
  const LIGHT = (() => {
    const v = [-0.45, -0.6, 0.66];
    const l = Math.hypot(...v);
    return v.map((x) => x / l);
  })();

  function drawShark() {
    const spine = wavySpine();
    const L = shark.length;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of spine) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
    const pad = L * 0.32;
    const c0 = Math.max(0, Math.floor((minX - pad) / CELL_W));
    const c1 = Math.min(view.cols - 1, Math.ceil((maxX + pad) / CELL_W));
    const r0 = Math.max(0, Math.floor((minY - pad) / CELL_H));
    const r1 = Math.min(view.rows - 1, Math.ceil((maxY + pad) / CELL_H));
    const segLen = [];
    for (let j = 0; j < N - 1; j++)
      segLen.push(Math.hypot(spine[j + 1][0] - spine[j][0], spine[j + 1][1] - spine[j][1]) || 1);
    ctx.fillStyle = pal.body;
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const px = (c + 0.5) * CELL_W, py = (r + 0.5) * CELL_H;
        let best = Infinity, bs = 0, bd = 0, bnx = 0, bny = 0, beyond = 0;
        for (let j = 0; j < N - 1; j++) {
          const a = spine[j], b = spine[j + 1];
          const vx = b[0] - a[0], vy = b[1] - a[1];
          let t = ((px - a[0]) * vx + (py - a[1]) * vy) / (segLen[j] * segLen[j]);
          let over = 0;
          if (j === N - 2 && t > 1) {
            over = (t - 1) * segLen[j];
            t = 1;
          } else t = Math.max(0, Math.min(1, t));
          const qx = a[0] + vx * t, qy = a[1] + vy * t;
          const dist = Math.hypot(px - qx, py - qy) + (over > 0 ? 0 : 0);
          if (dist < best) {
            best = dist;
            bs = (j + t) / (N - 1);
            bd = ((vx * (py - a[1]) - vy * (px - a[0])) / segLen[j]);
            bnx = -vy / segLen[j];
            bny = vx / segLen[j];
            beyond = over;
          }
        }
        const ad = Math.abs(bd) / L;
        let kind = 0; // 1 body, 2 fin, 3 tail
        let n = 0;
        if (beyond > 0) {
          // Forked tail: two lobes that spread and part past the last node.
          const k = beyond / (L * 0.17);
          if (k <= 1 && ad > 0.02 + 0.09 * k && ad < 0.05 + 0.15 * k) kind = 3;
        } else {
          const hw = halfWidth(bs);
          if (ad < hw) {
            kind = 1;
            n = bd / L / hw;
          } else if (inPectoral(bs, ad - hw) || ad < hw + pelvic(bs)) {
            kind = 2;
            n = Math.min(1, (ad - hw) / 0.22);
          } else if (bs > 0.86) {
            const k = (bs - 0.86) / 0.14;
            if (ad < 0.016 + 0.05 * k) kind = 3;
          }
        }
        if (!kind) continue;
        let bright;
        if (kind === 1) {
          const nz = Math.sqrt(Math.max(0, 1 - n * n));
          bright = 0.5 + 0.5 * (bnx * n * LIGHT[0] + bny * n * LIGHT[1] + nz * LIGHT[2]);
        } else bright = 0.45;
        const edge = kind === 1 && Math.abs(n) > 0.86;
        let glyph;
        if (edge) glyph = "'";
        else if (kind === 2) glyph = n < 0.35 ? "%" : n < 0.7 ? "t" : ";";
        else if (kind === 3) glyph = ":";
        else {
          // Dark water: bright glyphs read as lit. Light water: ink reads as
          // shadow, so keep the body dense and let the lit back thin out.
          const idx = pal.dark ? bright : 0.42 + (1 - bright) * 0.58;
          glyph = RAMP[Math.max(0, Math.min(RAMP.length - 1, Math.floor(idx * RAMP.length)))];
        }
        // Dorsal ridge and eyes.
        if (kind === 1 && bs > 0.34 && bs < 0.44 && Math.abs(n) < 0.09) glyph = "^";
        if (kind === 1 && bs > 0.06 && bs < 0.11 && Math.abs(Math.abs(n) - 0.62) < 0.2) glyph = "o";
        if (kind === 1 && bs > 0.15 && bs < 0.24 && Math.abs(n) > 0.55 && Math.abs(n) < 0.86 && Math.floor(bs * 60) % 2 === 0)
          glyph = "("; // gill slits
        ctx.globalAlpha = edge ? 0.45 : pal.dark ? 0.45 + bright * 0.55 : 0.7 + (1 - bright) * 0.3;
        ctx.fillText(glyph, c * CELL_W, r * CELL_H);
      }
    }
    ctx.globalAlpha = 1;
    // Wake from the tail.
    const tail = spine[N - 1];
    deposit(tail[0], tail[1], 0.55);
  }

  // ---------- fish ----------
  const fish = [];
  function spawnFish() {
    fish.length = 0;
    for (let s = 0; s < 3; s++) {
      const cx = view.w * (0.2 + 0.3 * s), cy = view.h * (0.3 + 0.2 * (s % 2));
      for (let i = 0; i < 12; i++) {
        fish.push({
          school: s,
          x: cx + (Math.random() - 0.5) * 80,
          y: cy + (Math.random() - 0.5) * 40,
          vx: (Math.random() - 0.5) * 40,
          vy: (Math.random() - 0.5) * 20,
          big: false,
          shade: 0.55 + Math.random() * 0.45,
        });
      }
    }
    for (let i = 0; i < 4; i++)
      fish.push({
        school: 3 + i,
        x: Math.random() * view.w,
        y: Math.random() * view.h,
        vx: (Math.random() - 0.5) * 30,
        vy: 0,
        big: true,
        shade: 0.8,
      });
  }

  function stepFish(dt) {
    const head = shark.nodes[0];
    const food = state.food ? toPx(state.food[0], state.food[1]) : null;
    const centers = new Map();
    for (const f of fish) {
      const c = centers.get(f.school) || { x: 0, y: 0, vx: 0, vy: 0, n: 0 };
      c.x += f.x; c.y += f.y; c.vx += f.vx; c.vy += f.vy; c.n++;
      centers.set(f.school, c);
    }
    for (const f of fish) {
      const c = centers.get(f.school);
      let ax = 0, ay = 0;
      if (c.n > 1) {
        ax += (c.x / c.n - f.x) * 0.6 + (c.vx / c.n - f.vx) * 0.8;
        ay += (c.y / c.n - f.y) * 0.6 + (c.vy / c.n - f.vy) * 0.8;
      }
      for (const o of fish) {
        if (o === f) continue;
        const dx = f.x - o.x, dy = (f.y - o.y) * 1.6;
        const d2 = dx * dx + dy * dy;
        if (d2 < 520) {
          ax += (dx / (d2 + 1)) * 900;
          ay += (dy / (d2 + 1)) * 900;
        }
      }
      if (food && !f.big) {
        const dx = food[0] - f.x, dy = food[1] - f.y;
        const d = Math.hypot(dx, dy) + 1;
        if (d < view.w * 0.6) {
          // Nibble: pull in, then mill around the pellet.
          const pull = d > 34 ? 90 : -30;
          ax += (dx / d) * pull - (dy / d) * 40;
          ay += (dy / d) * pull + (dx / d) * 40;
        }
      }
      // Flee the shark's head and body.
      const sx = f.x - head[0], sy = f.y - head[1];
      const sd = Math.hypot(sx, sy) + 1;
      const fear = shark.length * 0.75;
      let fleeing = false;
      if (sd < fear) {
        const k = (1 - sd / fear) * 900;
        ax += (sx / sd) * k;
        ay += (sy / sd) * k;
        fleeing = true;
      }
      ax += (Math.random() - 0.5) * 60;
      ay += (Math.random() - 0.5) * 30;
      // Soft walls.
      const m = 30;
      if (f.x < m) ax += (m - f.x) * 8;
      if (f.x > view.w - m) ax -= (f.x - view.w + m) * 8;
      if (f.y < m) ay += (m - f.y) * 8;
      if (f.y > view.h - m) ay -= (f.y - view.h + m) * 8;
      f.vx += ax * dt;
      f.vy += ay * dt * 0.7;
      const sp = Math.hypot(f.vx, f.vy);
      const max = fleeing ? 230 : f.big ? 45 : 85;
      const min = f.big ? 12 : 22;
      if (sp > max) { f.vx *= max / sp; f.vy *= max / sp; }
      if (sp < min) { f.vx *= min / (sp + 1e-3); f.vy *= min / (sp + 1e-3); }
      f.x += f.vx * dt;
      f.y += f.vy * dt;
      if (!f.big) deposit(f.x, f.y, 0.06);
    }
  }

  function drawFish() {
    ctx.fillStyle = pal.fish;
    for (const f of fish) {
      const right = f.vx >= 0;
      const g = f.big ? (right ? "><(((°>" : "<°)))><") : right ? "><>" : "<><";
      const x = Math.round(f.x / CELL_W) * CELL_W - (g.length * CELL_W) / 2;
      const y = Math.round(f.y / CELL_H) * CELL_H;
      ctx.globalAlpha = f.shade;
      ctx.fillText(g, x, y);
    }
    ctx.globalAlpha = 1;
  }

  // ---------- wake ----------
  let wake = new Float32Array(0);
  function deposit(x, y, v) {
    const c = Math.floor(x / CELL_W), r = Math.floor(y / CELL_H);
    if (c < 0 || r < 0 || c >= view.cols || r >= view.rows) return;
    const i = r * view.cols + c;
    wake[i] = Math.min(1, wake[i] + v);
  }

  // ---------- scenery ----------
  function drawWater(t) {
    const g = ctx.createRadialGradient(
      view.baseX, view.baseY - view.h * 0.62, 10,
      view.baseX, view.baseY - view.h * 0.5, Math.max(view.w, view.h) * 0.75,
    );
    g.addColorStop(0, pal.shallow);
    g.addColorStop(1, pal.deep);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, view.w, view.h);
    ctx.fillStyle = pal.water;
    const tt = t * 0.00005;
    for (let r = 0; r < view.rows; r++) {
      for (let c = 0; c < view.cols; c++) {
        const v = noise(c * 0.21 + tt * 6, r * 0.34 - tt * 4) * 0.6 + noise(c * 0.47 - tt * 9, r * 0.71 + tt * 5) * 0.4;
        if (v < 0.7) continue;
        ctx.globalAlpha = Math.min(0.22, (v - 0.7) * 1.3);
        ctx.fillText(v > 0.8 ? "≈" : v > 0.75 ? "~" : "-", c * CELL_W, r * CELL_H);
      }
    }
    const i = wake.length;
    ctx.fillStyle = pal.fish;
    for (let k = 0; k < i; k++) {
      const v = wake[k];
      if (v < 0.07) continue;
      ctx.globalAlpha = Math.min(0.55, v * 0.7);
      ctx.fillText(v > 0.4 ? "∘" : "·", (k % view.cols) * CELL_W, Math.floor(k / view.cols) * CELL_H);
    }
    ctx.globalAlpha = 1;
  }

  function label(text, x, y, align = "left") {
    ctx.font = `13px ${UI}`;
    ctx.textAlign = align;
    ctx.globalAlpha = 0.95;
    // A halo in the water color keeps labels readable over glyphs.
    ctx.lineWidth = 4;
    ctx.lineJoin = "round";
    ctx.strokeStyle = pal.deep;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = pal.label;
    ctx.fillText(text, x, y);
    ctx.textAlign = "left";
    ctx.globalAlpha = 1;
    ctx.font = `${FONT_PX}px ${MONO}`;
  }

  function drawScenery(t) {
    ctx.fillStyle = pal.sand;
    // Reach: a dotted sand ripple at 440 mm.
    const R = 440 * view.scale;
    for (let a = 0; a <= Math.PI; a += 0.035) {
      const x = view.baseX + Math.cos(a) * R, y = view.baseY - Math.sin(a) * R;
      ctx.globalAlpha = 0.45;
      ctx.fillText("·", x, y);
    }
    label("arm's reach", view.baseX - R * 0.74, view.baseY - R * 0.72, "right");
    // Kelp bed = pickup zone.
    for (const [[x0, y0], [x1, y1]] of state.layout.regions) {
      const [ax, ay] = toPx(x1, y1);
      const [bx, by] = toPx(x0, y0);
      const cA = Math.floor(ax / CELL_W), cB = Math.ceil(bx / CELL_W);
      const rA = Math.floor(ay / CELL_H), rB = Math.ceil(by / CELL_H);
      for (let r = rA; r < rB; r++) {
        for (let c = cA; c < cB; c++) {
          // Kelp grows in columns: a strand where the column hash says so.
          if (hash(c, 7) > 0.28 || hash(c, r) > 0.7) continue;
          const sway = Math.sin(t * 0.0012 + c * 0.9 + r * 0.45);
          ctx.globalAlpha = 0.3 + 0.35 * hash(c, 3);
          ctx.fillText(sway > 0.4 ? ")" : sway < -0.4 ? "(" : "|", c * CELL_W, r * CELL_H);
        }
      }
      ctx.globalAlpha = 0.8;
      ctx.strokeStyle = pal.sand;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([3, 5]);
      ctx.strokeRect(ax, ay, bx - ax, by - ay);
      ctx.setLineDash([]);
      label("pickup zone", ax, ay - 8);
    }
    // Shelf ledge.
    if (state.layout.shelf_drop_xy) {
      const [sx, sy] = state.layout.shelf_drop_xy;
      const [ax, ay] = toPx(sx + 60, sy + 50);
      const [bx, by] = toPx(sx - 60, sy - 50);
      for (let r = Math.floor(ay / CELL_H); r < Math.ceil(by / CELL_H); r++)
        for (let c = Math.floor(ax / CELL_W); c < Math.ceil(bx / CELL_W); c++) {
          ctx.globalAlpha = 0.38;
          ctx.fillText("╱", c * CELL_W, r * CELL_H);
        }
      label("shelf drop", bx + 8, (ay + by) / 2 + 4);
    }
    // Arm base: a reef.
    ctx.globalAlpha = 0.9;
    const reef = ["  ▄▟▙▄  ", " ▟████▙ "];
    reef.forEach((row, i) =>
      ctx.fillText(row, view.baseX - (row.length * CELL_W) / 2, view.baseY - CELL_H * (1.6 - i)),
    );
    label("arm base", view.baseX + 40, view.baseY + 2);
    ctx.globalAlpha = 1;
  }

  function drawFood(t) {
    if (!state.food) return;
    const [x, y] = toPx(state.food[0], state.food[1]);
    ctx.fillStyle = pal.food;
    for (let i = 0; i < 4; i++) {
      const a = t * 0.0011 + (i * Math.PI) / 2;
      ctx.globalAlpha = 0.7;
      ctx.fillText(i % 2 ? "·" : ":", x + Math.cos(a) * 16, y + Math.sin(a) * 9);
    }
    ctx.globalAlpha = 1;
    ctx.fillText("✺", x - CELL_W / 2, y - CELL_H / 2);
    label("block", x + 14, y - 10);
  }

  function drawToolTag() {
    if (!state.tool) return;
    const head = shark.nodes[0];
    label(`tool, ${state.tool[2].toFixed(0)} mm up`, head[0] + 16, head[1] - 14);
  }

  // ---------- frame ----------
  function resize() {
    const box = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = `${FONT_PX}px ${MONO}`;
    ctx.textBaseline = "top";
    CELL_W = Math.max(6, Math.ceil(ctx.measureText("M").width));
    const first = !view.w;
    view.w = box.width;
    view.h = box.height;
    view.cols = Math.ceil(view.w / CELL_W);
    view.rows = Math.ceil(view.h / CELL_H);
    view.scale = (view.h - 40) / 470;
    view.baseX = view.w / 2;
    view.baseY = view.h - 18;
    shark.length = Math.max(150, Math.min(320, view.h * 0.9));
    wake = new Float32Array(view.cols * view.rows);
    if (first) {
      placeShark(view.baseX - shark.length * 0.6, view.baseY - view.h * 0.55);
      spawnFish();
    }
    // Resizing clears the canvas; paint immediately instead of waiting.
    render(performance.now());
  }

  function render(t) {
    ctx.font = `${FONT_PX}px ${MONO}`;
    ctx.textBaseline = "top";
    drawWater(t);
    drawScenery(t);
    drawFood(t);
    drawFish();
    drawShark();
    drawToolTag();
    for (let i = 0; i < wake.length; i++) wake[i] *= 0.95;
  }

  let last = performance.now();
  let lastDraw = 0;
  let visible = true;
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const interval = reduced ? 500 : 33;
    if (visible && now - lastDraw >= interval) {
      const step = reduced ? 0.02 : Math.min(0.05, (now - lastDraw) / 1000);
      if (!reduced) {
        steerShark(step, now);
        stepFish(step);
      }
      render(now);
      lastDraw = now;
    }
    void dt;
    requestAnimationFrame(frame);
  }

  // ---------- data ----------
  function estimateFood(data) {
    const v = data.vision || {};
    const robot = data.robot || {};
    if (!v.fresh || !v.detections?.length || !state.calib?.aim_px || !robot.fresh) return null;
    if (v.settings?.mode !== "color") return null;
    const pose = robot.values?.pose;
    // The tabletop mapping is only valid looking straight down at camera height.
    if (!Array.isArray(pose) || Math.abs(pose[4]) > 5 || Math.abs(Math.abs(pose[3]) - 180) > 5) return null;
    const center = v.detections[0].center;
    const [[a, b], [c, d]] = state.calib.jacobian_px_per_mm;
    const ex = state.calib.aim_px[0] - center[0];
    const ey = state.calib.aim_px[1] - center[1];
    const det = a * d - b * c;
    if (!det) return null;
    return [pose[0] + (d * ex - b * ey) / det, pose[1] + (-c * ex + a * ey) / det];
  }

  async function loadStatic() {
    try {
      const [w, c] = await Promise.all([
        fetch("/api/workspace", { cache: "no-store" }).then((r) => r.json()),
        fetch("/api/calibration", { cache: "no-store" }).then((r) => r.json()),
      ]);
      state.layout = w;
      state.calib = c;
    } catch (_) {}
  }

  window.addEventListener("labdeck:status", (event) => {
    const data = event.detail;
    if (!data) {
      state.fresh = false;
      captionEl.textContent = "Link lost; the tank is frozen until it reconnects.";
      return;
    }
    const robot = data.robot || {};
    const pose = robot.fresh ? robot.values?.pose : null;
    state.tool = Array.isArray(pose) ? pose.slice(0, 3) : null;
    state.food = estimateFood(data);
    state.busy =
      data.job?.state === "running" || data.follow?.state === "running" || data.transfer?.state === "running";
    captionEl.textContent = state.tool
      ? `Tool at x ${state.tool[0].toFixed(0)}, y ${state.tool[1].toFixed(0)}, z ${state.tool[2].toFixed(0)} mm.`
      : "No arm telemetry right now.";
    // Throttled animation frames still get a current picture.
    const now = performance.now();
    if (now - lastDraw > 600) {
      render(now);
      lastDraw = now;
    }
  });

  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver((entries) => {
    visible = entries.some((e) => e.isIntersecting);
  }).observe(canvas);
  document.addEventListener("visibilitychange", () => (visible = !document.hidden));
  window.addEventListener("labdeck:theme", () => setTimeout(readPalette, 0));
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => setTimeout(readPalette, 0));
  readPalette();
  resize();
  loadStatic();
  setInterval(loadStatic, 15000);
  requestAnimationFrame(frame);
})();
