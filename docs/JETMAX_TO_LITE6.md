# Why JetMax could follow the block, and the next Lite 6 step

## What the JetMax code actually does

Inspection of the separate JetMax workspace found an implemented closed-loop image-centering routine:

1. Detect the green/cyan region and its centroid.
2. Measure its displacement from image center.
3. Convert displacement using a fixed `0.25 mm/pixel` scale and an empirically chosen axis mapping.
4. Rotate the correction according to the arm's base direction.
5. Apply a partial XY correction at a fixed approach height, limited to 12 mm per axis per iteration.
6. Wait for three distinct, fresh, consistent frames and measure again.
7. When centered, apply the camera-to-suction offset once (current constants: -37 mm and +5 mm in its calibrated reference frame).
8. Descend to the fixed pickup height and run the pump/lift/place sequence.

Relevant JetMax source: `lib/green_detect.py`, `scripts/web/arm_bridge.py::_center_on_target`, `_camera_to_arm`, `_tool_pick_xy`, and `_descend_and_suck`. Its source was read, not modified.

This was already an empirical calibration plus feedback loop. It could handle moved blocks within its camera view, working region, and height/orientation assumptions. The current JetMax suction state checks confirm pump command state; they are not an independent physical vacuum-seal measurement.

## Why the Lite 6 trial is different so far

The new deck detects color and runs YOLO, but returns image pixels only. The standalone motion trials used an operator-taught contact and verified short vertical paths. No code currently maps a detection to a Lite 6 motion target or performs iterative XY alignment.

The wrist camera and cup move and rotate together on the Lite 6. During manual positioning we observed substantial changes in wrist pitch. That changes how image axes relate to robot axes and where the cup projects into the image. JetMax constants cannot be transferred. A six-axis robot can still perform a simple fixed-orientation tabletop task; we can constrain the first experiment accordingly.

## Practical first version: fixed-height tabletop centering

A full general 3D picking system is not required for the first same-height block exercise. Reproduce the useful JetMax pattern with new measured values:

1. **Resolve release behavior first.** Keep the manufacturer OFF/release state asserted, inspect pickup input, and obtain operator confirmation of the physical result. No automatic repeat cycle while release remains uncertain.
2. **Teach an observation pose.** Operator selects/validates a clear pose where the camera sees the target region, with the cup facing the table and wrist orientation fixed. Record actual controller pose, tool offsets, image resolution, and target-top plane height. Returning to this pose is a separate reviewed motion, not a guessed home position.
3. **Calibrate a suction aim point.** Starting from an operator-verified cup-over-marker relationship, observe that same stationary marker at the chosen hover height and orientation. Its image location gives an empirical aim point for where this cup aligns with that target plane; it need not be image center. Maintain those height/orientation conditions. Tool offsets must be accounted for once.
4. **Measure XY response.** With a stationary target and supervised small known X and Y movements at the observation height, record fresh before/after pixel locations and actual robot positions. Fit a local 2×2 image-motion relationship (or a planar mapping where appropriate) instead of guessing axis signs or millimeters per pixel. Validate sign, scale, and alignment on withheld positions across the intended region.
5. **Build align-only first.** Above a validated clearance, take a fresh stable detection, calculate a bounded partial XY correction toward the aim point, move/settle, and reacquire. Cap correction size, total travel, iterations, and elapsed time. Stop on stale/lost/jumping targets or changed wrist/height/configuration. No Z descent during alignment.
6. **Add a single pickup.** After align-only passes, descend only to the validated block-top/contact height for the measured object class and working plane; confirm seal before lifting. Validate release before returning to observation.

A single global homography is not reusable as a wrist camera changes pose. A local image-motion relationship also has a limited validated operating range. For variable heights, orientation changes, wider reach, or 3D picking, add appropriate hand-eye calibration and validated color-aligned depth rather than extending the tabletop assumptions silently.

## Iterative tracking and retry are separate loops

**Alignment loop:** repeatedly observe → bounded XY correction → settle → observe, while remaining above clearance. This is the behavior that made JetMax follow a moved block.

**Pickup recovery:** a failed suction attempt does not authorize repeated downward pressure. End suction/release, verify tool state, retract along a validated path if conditions permit, reacquire the target, and allow only a small explicit retry budget after identifying a recoverable cause. Stop on uncertain contact height, changing object identity, lost target, release failure, controller fault, or exhausted budget. A restart/refresh must never resume an interrupted physical action automatically.

Suggested inspectable states:

```text
idle → observation → acquire stable target → align-only → alignment verified
     → reviewed approach → contact → confirm suction → lift → hold/place
     → command release → verify release → retract → observation
```

Faults transition to an explicit operator-recovery state; they do not skip gates. Logs should include frame sequence, timestamp, robot pose, image error, proposed/actual displacement, feedback, and transition reason. The UI should distinguish observation, dry-run prediction, alignment-only, and pickup execution.

## Teaching outcome

Students can compare an empirical fixed-height controller with a full geometric calibration, and explain where each is valid. They should also distinguish output commands, sensor observations, physical operator observations, and validated measurements. No automatic tracking or retry capability should be claimed before the corresponding measurements and tests exist.
