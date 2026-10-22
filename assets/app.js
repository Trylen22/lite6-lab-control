/* Browser lesson: HTTP carries observations and host-only vision settings.
 * There is deliberately no keyboard/mouse robot control and no motion fetch().
 * All hardware-derived text uses textContent, never interpolated HTML.
 */
"use strict";
const $ = (id) => document.getElementById(id);
let currentMode = "color";
let maskVisible = false;
let pending = false;
let initialized = false;
let recovering = false;
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
  $("view-caption").textContent = maskVisible
    ? "HSV THRESHOLD MASK"
    : { color: "COLOR OVERLAY", raw: "RAW COLOR", yolo: "YOLO OBJECT OVERLAY" }[
        mode
      ];
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
        cell(item.label),
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
  } catch (error) {
    recovering = true;
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
  }
}
// A completion-based timer prevents piling up status requests on a slow network.
async function poll() {
  await refresh();
  setTimeout(poll, 750);
}
setModePresentation("color");
poll();
