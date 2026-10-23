/* Browser lesson: observations/settings are separate from one explicit pickup.
 * One button POST requests one guarded cycle; no coordinates enter the request.
 * All hardware-derived text uses textContent, never interpolated HTML.
 */
"use strict";
const $ = (id) => document.getElementById(id);
let currentMode = "color";
let maskVisible = false;
let pending = false;
let initialized = false;
let recovering = false;
let startingPickup = false;
let followToken = null;
let followRunning = false;
let startingFollow = false;
const pageNames = {
  workspace: "Vision workspace",
  robot: "Robot telemetry",
  learn: "Learning path",
  system: "System notes",
};

function showPage(name) {
  for (const page of document.querySelectorAll(".page"))
    page.hidden = page.id !== name;
  for (const button of document.querySelectorAll("[data-page]")) {
    button.classList.toggle("active", button.dataset.page === name);
    if (button.dataset.page === name)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  $("breadcrumb").textContent = pageNames[name];
  window.scrollTo({ top: 0, behavior: "smooth" });
}
document
  .querySelectorAll("[data-page]")
  .forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));
document
  .querySelectorAll("[data-go]")
  .forEach((b) => b.addEventListener("click", () => showPage(b.dataset.go)));

function dot(id, good) {
  $(id).className = "dot " + (good ? "good" : "bad");
}
function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}
function format(value, digits = 1) {
  return Number.isFinite(value) ? value.toFixed(digits) : "—";
}
function measurementGrid(id, labels, values) {
  const target = $(id);
  target.replaceChildren();
  labels.forEach((label, i) => {
    const div = document.createElement("div"),
      span = document.createElement("span"),
      strong = document.createElement("strong");
    span.textContent = label;
    strong.textContent = format(values?.[i]);
    div.append(span, strong);
    target.append(div);
  });
}
function telemetry(robot) {
  const values = robot.fresh ? robot.values : {};
  const rows = [
    [
      "SDK connection",
      robot.fresh ? "Receiving telemetry" : "Unavailable / stale",
    ],
    ["Controller version", values.version || "—"],
    ["Controller state", values.state == null ? "—" : `Code ${values.state}`],
    [
      "Error / warning",
      Array.isArray(values.errors) ? values.errors.join(" / ") : "—",
    ],
    [
      "Last SDK update",
      robot.age_seconds == null ? "—" : `${robot.age_seconds.toFixed(1)} s ago`,
    ],
    ["Read detail", robot.error || "Getters only; no robot commands"],
  ];
  const list = $("robot-details");
  list.replaceChildren();
  for (const [key, value] of rows) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    list.append(dt, dd);
  }
  measurementGrid(
    "pose-grid",
    ["X / mm", "Y / mm", "Z / mm", "ROLL / °", "PITCH / °", "YAW / °"],
    values.pose,
  );
  // SDK may return a seventh placeholder for a six-axis Lite 6. Show six axes.
  measurementGrid(
    "joint-grid",
    ["J1 / °", "J2 / °", "J3 / °", "J4 / °", "J5 / °", "J6 / °"],
    values.joints,
  );
}
function setModePresentation(mode) {
  currentMode = mode;
  $("hand-controls").hidden = mode !== "hands";
  $("calibration-summary").hidden = mode === "hands";
  $("pickup-controls").hidden = mode === "hands";
  if (mode === "hands") $("cup-aim-guide").hidden = true;
  document.querySelectorAll("[data-mode]").forEach((b) => {
    b.classList.toggle("selected", b.dataset.mode === mode);
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
  });
  $("color-settings").hidden = mode !== "color";
  $("yolo-settings").hidden = mode !== "yolo";
  $("raw-settings").hidden = mode !== "raw";
  $("mask-toggle").disabled = mode !== "color";
  $("mode-metric").textContent = {
    color: "Color / HSV",
    raw: "Raw camera",
    yolo: "YOLOX-Nano",
    hands: "Hands / gestures",
  }[mode];
  $("lesson-intro").textContent =
    mode === "yolo"
      ? "Learned classes become boxes through explicit preprocessing and decoding."
      : mode === "raw"
        ? "Begin with the image itself before adding an interpretation."
        : "Color detection is a sequence of small, inspectable decisions.";
  $("step-two-title").textContent =
    mode === "yolo"
      ? "Prepare the model input"
      : mode === "raw"
        ? "Read the color image"
        : "Select a color range";
  $("step-two-body").textContent =
    mode === "yolo"
      ? "Resize with preserved aspect ratio and pad to 416 × 416."
      : mode === "raw"
        ? "The sensor image arrives as BGR pixels."
        : "Convert BGR to HSV, then keep matching pixels.";
  $("step-three-title").textContent =
    mode === "yolo"
      ? "Predict & filter boxes"
      : mode === "raw"
        ? "Compare the scene"
        : "Find useful shapes";
  $("step-three-body").textContent =
    mode === "yolo"
      ? "Run CPU inference, decode coordinates, and suppress duplicates."
      : mode === "raw"
        ? "No detector runs in raw mode."
        : "Clean the mask and reject small or narrow regions.";
  if (mode === "hands") {
    $("lesson-intro").textContent =
      "Follow a palm through local hand landmarks and gesture recognition.";
    $("step-two-title").textContent = "Find 21 hand landmarks";
    $("step-two-body").textContent =
      "A local model finds finger joints and a palm center.";
    $("step-three-title").textContent = "Recognize the gesture";
    $("step-three-body").textContent =
      "Open palm follows; a fist sends the arm back to its ready pose.";
  }
  $("view-caption").textContent = maskVisible
    ? "HSV THRESHOLD MASK"
    : {
        color: "COLOR OVERLAY",
        raw: "RAW COLOR",
        yolo: "YOLO OBJECT OVERLAY",
        hands: "HAND LANDMARKS",
      }[mode];
}
function changeStreamView() {
  $("camera-image").src =
    "/stream.mjpg?view=" +
    (maskVisible ? "mask" : "annotated") +
    "&session=" +
    Date.now();
  $("mask-toggle").setAttribute("aria-pressed", String(maskVisible));
  $("mask-toggle").textContent = maskVisible
    ? "◧ Show camera overlay"
    : "◧ Show threshold mask";
  setModePresentation(currentMode);
}
$("mask-toggle").addEventListener("click", () => {
  maskVisible = !maskVisible;
  changeStreamView();
});

async function goToStart(task) {
  try {
    const response = await fetch("/api/go-start", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Labdeck-Action": "go-start",
      },
      body: JSON.stringify({ task }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Move to start failed");
  } catch (error) {
    $(task === "hand" ? "follow-message" : "pickup-message").textContent =
      error.message;
  }
}

async function configure(patch) {
  if (pending) return;
  pending = true;
  $("settings-message").textContent = "Applying observation settings…";
  try {
    const response = await fetch("/api/vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error);
    if (patch.mode) {
      maskVisible = false;
      setModePresentation(patch.mode);
      changeStreamView();
      // Picking a demo tab is the operator's request to move to its start
      // pose. Page loads and status polling never move the arm.
      const task = { color: "pickup", hands: "hand" }[patch.mode];
      if (task) await goToStart(task);
    }
    $("settings-message").textContent =
      "Observation settings applied to the host.";
  } catch (error) {
    $("settings-message").textContent = error.message;
  } finally {
    pending = false;
    await refresh();
  }
}
document
  .querySelectorAll("[data-mode]")
  .forEach((b) =>
    b.addEventListener("click", () => configure({ mode: b.dataset.mode })),
  );
$("preset").addEventListener("change", () =>
  configure({ preset: $("preset").value }),
);
$("min-area").addEventListener(
  "input",
  () => ($("area-value").textContent = $("min-area").value + " px²"),
);
$("min-area").addEventListener("change", () =>
  configure({ min_area: Number($("min-area").value) }),
);
$("confidence").addEventListener(
  "input",
  () => ($("confidence-value").textContent = $("confidence").value + "%"),
);
$("confidence").addEventListener("change", () =>
  configure({ confidence: Number($("confidence").value) / 100 }),
);

// Only this page's explicit Start response grants heartbeat ownership. Reading
// status never renews it. A closed/disconnected/hidden page cannot keep following.
async function followAction(action, body = {}) {
  const response = await fetch(`/api/follow/${action}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Labdeck-Action": "hand-follow",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(2000),
    keepalive: action === "stop",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Follow request failed");
  return result;
}
async function stopFollowing() {
  followToken = null;
  try {
    await followAction("stop");
  } catch (error) {
    $("follow-message").textContent = error.message;
  }
}
$("follow-start").addEventListener("click", async () => {
  startingFollow = true;
  $("follow-start").disabled = true;
  try {
    const result = await followAction("start");
    followToken = result.token;
  } catch (error) {
    $("follow-message").textContent = error.message;
  } finally {
    startingFollow = false;
  }
});
$("follow-stop").addEventListener("click", stopFollowing);
async function renewFollow() {
  if (followToken) {
    try {
      await followAction("heartbeat", { token: followToken });
    } catch {
      followToken = null;
    }
  }
  setTimeout(renewFollow, 400);
}
renewFollow();
document.addEventListener("visibilitychange", () => {
  if (document.hidden && followToken) stopFollowing();
});
window.addEventListener("pagehide", () => {
  if (followToken) stopFollowing();
});

async function refresh() {
  try {
    const response = await fetch("/api/status", {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) throw new Error("Status unavailable");
    const data = await response.json(),
      v = data.vision,
      r = data.robot;
    if (recovering) {
      recovering = false;
      changeStreamView();
    }
    dot("camera-dot", v.fresh);
    dot("stream-dot", v.fresh);
    dot("robot-dot", r.fresh);
    $("camera-state").textContent = v.fresh ? "Streaming" : "Unavailable";
    $("camera-detail").textContent = v.fresh
      ? `640 × 400 · ${v.age_seconds.toFixed(2)}s frame age`
      : "Waiting for fresh frames";
    $("robot-state").textContent = r.fresh ? "Connected" : "Unavailable";
    $("live-label").textContent = v.fresh ? "● LIVE" : "FEED UNAVAILABLE";
    $("stale-overlay").hidden = v.fresh;
    if (!v.fresh)
      $("stale-overlay").textContent =
        v.error || "Waiting for a fresh camera frame…";
    $("fps").textContent = v.fresh ? v.fps.toFixed(1) : "—";
    $("processing-detail").textContent =
      `Laptop CPU · ${v.processing_ms.toFixed(1)} ms / frame`;
    $("candidate-count").textContent = v.fresh ? v.detections.length : "—";
    $("result-count").textContent = v.fresh
      ? `${v.detections.length} FOUND`
      : "NO FRESH DATA";
    // Keep sliders responsive during dragging; synchronize after a POST or on
    // first load, rather than overwriting a student's in-progress input.
    if (
      !initialized ||
      (!pending &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "SELECT")
    ) {
      $("preset").value = v.settings.preset;
      $("min-area").value = v.settings.min_area;
      $("area-value").textContent = v.settings.min_area + " px²";
      $("confidence").value = Math.round(v.settings.confidence * 100);
      $("confidence-value").textContent =
        Math.round(v.settings.confidence * 100) + "%";
      initialized = true;
    }
    if (currentMode !== v.settings.mode) {
      maskVisible = false;
      setModePresentation(v.settings.mode);
      changeStreamView();
    }
    $("hsv-note").textContent = v.hsv_ranges
      .map(
        (range) =>
          `HSV [${range.slice(0, 3).join(", ")}] → [${range.slice(3).join(", ")}]`,
      )
      .join(" · ");
    const body = $("detections");
    body.replaceChildren();
    for (const item of v.detections) {
      const row = document.createElement("tr");
      const position = item.center
        ? `(${item.center.join(", ")}) px`
        : `${item.bbox.join(", ")} px`;
      row.append(
        cell(
          item.gesture ? `${item.handedness} / ${item.gesture}` : item.label,
        ),
        cell(position),
        cell(
          item.confidence == null
            ? `${item.area_px} px²`
            : `${Math.round(item.confidence * 100)}%`,
        ),
      );
      body.append(row);
    }
    $("empty-state").hidden = v.detections.length > 0;
    telemetry(r);
    const job = data.job || {
      state: "unavailable",
      message: "Pickup unavailable",
    };
    const running = job.state === "running";
    const transfer = data.transfer || {};
    const moving = transfer.state === "running";
    followRunning = data.follow?.state === "running";
    if (!followRunning) followToken = null;
    $("follow-start").disabled =
      startingFollow || running || followRunning || !data.follow_ready?.ready;
    $("follow-stop").disabled = !followRunning;
    $("follow-message").textContent = followRunning
      ? data.follow.message
      : (moving || transfer.state === "failed") && transfer.task === "hand"
        ? transfer.message
        : data.follow_ready?.reason || "Following unavailable";
    $("pick-place").disabled =
      startingPickup || running || followRunning || !data.pickup?.ready;
    $("pick-place").textContent = running ? "Cycle running…" : "Pick & Place";
    $("pick-shelf").disabled = $("pick-place").disabled;
    $("pickup-phase").textContent = running
      ? job.phase.replaceAll("_", " ")
      : job.state === "complete"
        ? "Cycle complete"
        : job.state === "failed"
          ? "Cycle stopped"
          : "Ready for checks";
    $("pickup-message").textContent =
      running || job.state === "complete" || job.state === "failed"
        ? job.message
        : (moving || transfer.state === "failed") && transfer.task === "pickup"
          ? transfer.message
          : data.pickup?.reason || "Pickup unavailable";
    // Display-only listeners (viz.js, creature.js) read the same snapshot.
    window.dispatchEvent(new CustomEvent("labdeck:status", { detail: data }));
  } catch (error) {
    recovering = true;
    $("pick-place").disabled = true;
    $("pick-shelf").disabled = true;
    $("follow-start").disabled = true;
    followToken = null;
    $("pickup-phase").textContent = "Disconnected";
    $("pickup-message").textContent =
      "Waiting for the local dashboard. Closing the page does not stop an active cycle.";
    $("camera-state").textContent = "Disconnected";
    $("robot-state").textContent = "Unavailable";
    ["camera-dot", "stream-dot", "robot-dot"].forEach((id) => dot(id, false));
    $("stale-overlay").hidden = false;
    $("stale-overlay").textContent = "Dashboard connection lost. Reconnecting…";
    $("live-label").textContent = "DISCONNECTED";
    $("candidate-count").textContent = "—";
    $("detections").replaceChildren();
    $("result-count").textContent = "NO FRESH DATA";
    $("empty-state").hidden = false;
    $("fps").textContent = "—";
    telemetry({
      fresh: false,
      values: {},
      error: "Dashboard connection lost",
      age_seconds: null,
    });
    window.dispatchEvent(new CustomEvent("labdeck:status", { detail: null }));
  }
}
// A completion-based timer prevents piling up status requests on a slow network.
async function poll() {
  await refresh();
  setTimeout(poll, 750);
}
setModePresentation("color");
poll();

// A saved fit explains the experiment; it never sends movement commands.
async function refreshCalibration() {
  try {
    const response = await fetch("/api/calibration", {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    const fit = await response.json();
    const guide = $("cup-aim-guide");
    guide.hidden = !fit.aim_px || currentMode === "hands";
    if (fit.aim_px) {
      guide.style.left = `${(100 * (fit.resolution[0] - 1 - fit.aim_px[0])) / fit.resolution[0]}%`;
      guide.style.top = `${(100 * (fit.resolution[1] - 1 - fit.aim_px[1])) / fit.resolution[1]}%`;
    }
    $("calibration-detail").textContent =
      fit.status === "tabletop_profile"
        ? "Validated fixed-height tabletop profile · one green block · return to camera height after release."
        : fit.status === "placement_guide_only"
          ? "Arm relocated and idle. Slide the green marker onto the yellow CUP AIM guide. New contact teaching is required."
          : fit.aim_px
            ? `Recorded aim (${fit.aim_px.map((x) => x.toFixed(1)).join(", ")}) px · fit error ${fit.max_residual_px.toFixed(2)} px. Valid only at the taught height and wrist orientation.`
            : "No recorded XY fit. Pixels are not pickup coordinates.";
  } catch (_) {
    $("cup-aim-guide").hidden = true;
    $("calibration-detail").textContent = "Calibration status unavailable.";
  }
}
refreshCalibration();
setInterval(refreshCalibration, 3000);

// Only a deliberate click starts hardware work. Never invoke this from poll().
async function startPickup(button, body) {
  if (startingPickup || button.disabled) return;
  startingPickup = true;
  $("pick-place").disabled = true;
  $("pick-shelf").disabled = true;
  $("pickup-phase").textContent = "Starting checks";
  try {
    const response = await fetch("/api/pick-place", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Labdeck-Action": "pick-place",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Pickup could not start");
    $("pickup-message").textContent = result.message;
  } catch (error) {
    $("pickup-phase").textContent = "Start not confirmed";
    $("pickup-message").textContent =
      error.message + ". Check status before trying again.";
  } finally {
    startingPickup = false;
    await refresh();
  }
}
$("pick-place").addEventListener("click", () =>
  startPickup($("pick-place"), {}),
);
$("pick-shelf").addEventListener("click", () =>
  startPickup($("pick-shelf"), { destination: "shelf" }),
);
