# Project instructions

## Scope

This repository owns Lite 6 and OAK-D Pro PoE work. Do not modify, deploy to, or commit changes in the sibling JETMAX project as part of this work. Do not copy its credentials, device addresses, motion limits, saved poses, or camera offsets here.

## Device work

Start with local inspection and read-only device status. Do not enable motion, release brakes, change I/O, operate a tool, reset network settings, flash firmware, or configure automatic startup without a concrete user request covering that operation. Confirm which physical device is being addressed. Before motion, establish the mounting, reachable emergency stop, tool/payload configuration, workspace, and low-speed trial with the operator present.

Do not reuse JetMax coordinates, calibration, or motion code as Lite 6 defaults. Do not make an example command move hardware on import or startup. Keep observation, manual motion, and automation separate. Document actual stop behavior; a dashboard stop is not automatically an emergency stop.

## Configuration and version control

Keep actual machine configuration and credentials under ignored `local/` or outside the repository. Commit sanitized examples. Do not embed secrets in scripts or remote URLs. Review staged content before pushing. Keep this repo private unless the user requests otherwise.

Pin dependencies after confirming host and device compatibility. Record changes, checks, and remaining physical validation in docs/STATUS.md. Push completed work to this project's GitHub remote as requested by the user; never claim a push succeeded without checking it.

## Classroom purpose

The user requires this repo to be heavily commented, educational, and clean. Explain units, coordinate frames, preprocessing assumptions, SDK return codes, concurrency boundaries, and failure handling near the relevant code. Keep modules focused, format browser assets for reading, and maintain exercises, architecture, and an incremental roadmap in docs/. Never describe pixel detections as calibrated pickup targets. The user subsequently authorized one supervised pickup, a two-second hold, and release with the operator at the emergency stop. This authorization does not supply verified target/contact coordinates, TCP/tool configuration, or calibration. Two initial cycles stopped at attachment timeout before motion. After the operator adjusted contact, a stationary test confirmed feedback 1, and one explicitly authorized 2 mm upward lift/two-second hold/release-at-hover trial completed. There was no commanded descent into the compressed contact. Final pose and tool-off state were verified; actual object clearance is not independently measured. Preserve the feedback gate and the distinction between measured robot travel, cup compliance, operator observations, and camera calibration. Further repetitions or larger motions require a fresh concrete user request and validated current geometry. Establish those prerequisites before implementing/executing this specific cycle; do not broaden it into repeated automation.

## Latest supervised trial and release finding

The user authorized a 10 mm lift after the successful 2 mm test. The controller completed the bounded 10 mm sequence, but the user reported vacuum did not shut off. A no-motion correction sent the manufacturer OFF/release state (DO0 low, DO1 high) and left it asserted. Prior code's extra reset of DO1 to low was an unvalidated assumption and is now removed. Both scripts now verify OFF/release outputs plus pickup input low; do not reintroduce an all-low tool baseline or call a command ACK physical release. Operator physical pump/block confirmation remains distinct from I/O. No additional movement is authorized by the subsequent planning/comparison questions.

## Current calibration authorization and manual handoff

The user's latest concrete request authorizes supervised green-block movement
calibration and coordinated pickup development. Physical release and suction
stopped were explicitly confirmed. This supersedes the earlier statement that
planning questions alone did not authorize movement. Upward-only observation
positioning has reached Z=200 mm. The operator then offered to jog the camera
into view: no autonomous movement may overlap this manual handoff. Re-read the
pose and reconcile it with the taught XY/orientation before resuming. XY response
sampling and align-only motion have not been validated on hardware; descent and
pickup need a validated aiming/contact relationship. Keep a bounded controller,
seal feedback and the corrected release state. Gesture requests describe future
work, not permission for unrestricted motion.

## Measured alignment and current pickup blocker

Subsequent operator vertical jogging reached a useful view. A local 20 mm XY
response fit and independent checks passed, then a +5/+5 mm offset was corrected
in five bounded image-guided moves. Operator confirmed block unchanged. Full
pickup descent preflight then rejected wrist IK discontinuity near contact;
NO descent/tool activation occurred. Current arm is idle at observation height,
release I/O checked. Preserve this guard. Establish and validate a different
continuous posture/path and re-teach contact before picking. Calibration is a
local fixed-height experiment, not a general workspace or gesture policy.

## Authorized relocation and placement handoff

User subsequently requested moving the setup for pickup and confirmed clear
space. Empty wrist moved +40 mm base X at fixed observation height in two slow
segments; final idle/release verified. Previous fit archived and invalidated.
UI yellow CUP AIM is now placement guidance only, not active pickup calibration.
Operator has been asked to slide the green marker onto it, remove their hand
and report positioned. Do not move while the operator is placing the block.
New contact teaching and fresh calibration checks remain necessary.

## Relocated block clearance checkpoint

Operator reported block placed on guide. Live checks passed; two small XY guide
corrections and a bounded vertical approach completed. Current arm is idle at
10 mm above the historical sealed floor (this is NOT measured physical gap),
manufacturer release outputs verified, no faults. Operator is being asked if
cup is centered with a gap, off-center, or already touching. Wait for physical
contact information before further descent; no newly taught contact or suction
has occurred. Keep the arm stationary during this inspection/handoff.

## Successful relocated pickup and authorized faster repeat

Physical cup inspection reported centered and approximately 5 mm above contact.
A bounded search sealed after 4 mm; 10 mm lift/hold/lower/release completed.
Operator confirmed lift, then explicitly requested one return/repeat at 15%
higher movement speeds with continuous approaches. A seal timeout caused no
lift and released at contact. Restored suction-before-final-descent. Live ON
ACK/all-low readback required a checked individual-output fallback; do not
assume the SDK paired call actually enabled the pump. `labdeck.suction` now
verifies states and preserves an already-ON seal. Same-floor faster repeat then
completed, with final idle/release verified. No extra cycle is authorized by
this completed repeat. Current taught floor is the NEW relocated seal floor;
never fall back to the old deeply compressed contact. General workspace and
gesture motion remain out of scope. Active old calibration stays invalidated.
