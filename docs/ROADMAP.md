# Staged development plan

The goal is a readable classroom repository that progresses from observation to optical recognition and supervised pick-and-place. Current authorization is UI, SDK exploration, and vision; robot motion is explicitly excluded.

## Phase 1 — Observation and vision (current)

Deliverables:

- Independent Lite 6 repository and device configuration.
- Stable camera input, local UI, and read-only SDK telemetry.
- Inspectable OpenCV color detection and local YOLO inference.
- Educational comments, architecture notes, offline checks, and teaching exercises.

Verified: both SDK and camera respond; live raw/color/YOLO processing works; offline vision and read-only boundary checks pass. Browser rendering/manual interaction review remains a separate checkpoint because browser automation was unavailable in this session.

Remaining observations: examine the rendered UI with the operator, tune thresholds under actual lighting, measure ordinary-object YOLO performance, and identify the exact tool/camera mounting arrangement. No trained lab-part recognizer is claimed.

## Phase 2 — Measurement and calibration (no motion initially)

1. Document fixed versus wrist-mounted camera geometry and the attached tool.
2. Inspect the factory stereo calibration and validate depth on known objects if depth will be used.
3. Define image, camera, robot-base, and tool coordinate frames explicitly.
4. Choose the calibration method appropriate to the mounting and working plane/3D task.
5. Store calibration provenance, units, residual errors, and the validated working region.
6. Validate on reference points excluded from fitting. Quantify error rather than relying on an overlay looking aligned.
7. Render proposed robot-space targets as a dry-run overlay; do not command them.

Checkpoint: a documented transform, independent accuracy measurements, freshness/uncertainty rules, and clear rejection of targets outside the validated region. A model's class score alone is insufficient validation.

## Phase 3 — Supervised manual movement (future authorization)

Before implementation or execution, obtain explicit authorization for robot motion and establish:

- Secure mounting, reachable working emergency stop, and clear workspace.
- Correct tool, payload, tool center point, and collision/speed settings.
- This arm's workspace and poses; no JetMax coordinates or physical offsets.
- Measured controller behavior and stopping behavior, including network loss.
- Separation between UI observation, operator command requests, and physical execution.

Start with supervised small low-speed steps. Document each SDK command and why it is used. Do not silently enable motion, clear faults, change modes, or home on startup.

Checkpoint: repeatable supervised manual operation with a documented recovery procedure. A browser button is not a hardware emergency stop.

## Phase 4 — Supervised single pick-and-place

Build an explicit, commented state machine:

```text
observe → validate → approve target → approach → pick
        → verify attachment → lift → transfer → release → verify placement
```

Document which measurements confirm each transition. Reject stale, uncertain, unreachable, or out-of-workspace targets. Establish what happens on target loss, suction/gripper failure, blocked destination, dropped object, or interrupted motion. Command acknowledgement is not proof of physical attachment.

Checkpoint: repeated single-cycle trials with measured pickup/placement error and logged failures. Keep automatic repetition separate from a single supervised cycle.

## Phase 5 — Repeatability and deployment

Only after earlier checkpoints: evaluate the spare Nano or a lab PC, remote access, process supervision, trained lab-part models, possible on-camera YOLO, and optional PLC integration. Compare CPU, memory, latency, and model accuracy on the chosen host. The current laptop dependency pins are not evidence of original Nano compatibility.

Each milestone should have a small commit, updated teaching notes, explicit validation, and a confirmed push to this project's private GitHub repository.
