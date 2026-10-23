# Project status

## 2026-10-22 — Separate project initialization

- Workspace: `/home/wavyjones/Desktop/LITE6`.
- Intended GitHub repository: `Trylen22/lite6-lab-control` (private).
- Known hardware from discussion: UFACTORY Lite 6, label model LI10; Luxonis OAK-D Pro PoE.
- Host decision pending: existing lab PC versus spare original Jetson Nano dev kit.
- JetMax remains a separate project with its existing local changes untouched.
- Added setup documentation, ignored local configuration, project instructions, and local host-inventory script.
- No device connection or physical control has been attempted for this project.
- No hardware SDK dependencies installed or pinned yet; compatibility is unverified.

## Next session

Identify existing lab wiring, tool, emergency stop, addresses, and host. Record system inventory. Start with status and camera viewing; motion and automation follow separate verification.

## Validation

Passed: shell syntax check, local host-inventory execution on the development workstation, example TOML parsing, ignored local configuration/capture/secret path checks, and staged whitespace/content review. The local inventory output is ignored. Physical functionality remains untested. GitHub synchronization is verified separately after publishing.

## First lab network attempt

- Operator supplied a robot web endpoint; stored only in ignored local configuration.
- Created a dedicated laptop Ethernet profile with a static address, no default gateway, duplicate-address detection, and autoconnect disabled. Wi-Fi configuration unchanged.
- Target ping and HTTP requests timed out. Final inspection showed Ethernet carrier off, so connectivity and device identity remain unverified.
- Next: restore physical Ethernet link and retry only the supplied endpoint. No robot settings or motion commands were sent.

## Lab web connectivity confirmed

- Operator corrected the target address, recorded in ignored local configuration.
- Ethernet ping: two replies, zero packet loss.
- HTTP on port 18333: 200 OK; page title UFactory Studio.
- Network and web connectivity are now established. Robot identity, status, and camera access remain to be inspected. No motion or robot configuration commands sent.

## Camera discovery attempt

- Ethernet-only discovery found one additional responding address besides the arm and laptop. This remains an unverified camera candidate and may be switch infrastructure. Actual address and MAC are stored locally.
- No open TCP 11490 result in a limited subnet probe; DepthAI discovery returned zero devices. Neither check establishes camera absence.
- Added a discovery-only utility and pinned the dependency versions installed in this project's ignored virtual environment on the Linux x86_64/Python 3.12 laptop. Original Nano compatibility is not established.
- Utility executed successfully and reported zero devices. No camera stream, firmware update, configuration write, or robot motion was initiated.
- Next: confirm camera power/link and compare the label MAC with the candidate address, then repeat discovery.

## Additional candidate identification

- Additional responding device offers SSH (Dropbear 2020.81), with tested web/RTSP/DepthAI ports closed.
- MAC vendor lookup indicates Ubiquiti; the device is likely network infrastructure, but exact model has not been confirmed. Vendor discovery query received no reply.
- No authentication, device configuration change, or stream initialization was attempted. Camera identification remains pending.

## Camera found on documented fallback subnet

- Checked Luxonis PoE guide: DHCP fallback is `169.254.1.222` in the link-local range.
- Added a secondary laptop Ethernet link-local address and explicit link-local route while retaining the arm subnet and Wi-Fi. Saved both to the dedicated profile; autoconnect remains disabled.
- Camera fallback address responded to two source-bound pings with zero packet loss. DepthAI listed one TCP/IP device in `X_LINK_BOOTLOADER` state.
- Stored camera endpoint and MAC locally; documented reproducible network approach. No camera configuration, firmware, pipeline, or robot motion changes.
- Next: verify camera model and inspect an image stream on operator request.

## Local color stream verified

- Connected explicitly to the confirmed OAK endpoint and started a temporary CAM_A color pipeline. Device reports OAK-D-PRO-POE, OV9782 color sensor, and two OV9282 mono sensors.
- Added localhost-only preview server with a bounded frame queue, frame freshness reporting, current JPEG, and MJPEG. Requested 640 x 400 at 15 FPS.
- Verified fresh health response and decoded/visually inspected a current JPEG. A two-second MJPEG sample contained 31 frame boundaries. Verified script syntax.
- Preview URL on the laptop: http://127.0.0.1:8090/ . Process intentionally remains running for the operator. Browser automation was unavailable, so the page must be opened by the operator; HTTP and image delivery were verified directly.
- Dependencies pinned for this laptop in requirements-preview.txt. Diagnostic images remain ignored locally. No continuous recording, firmware flash, persistent camera settings, IR emitter commands, or arm control.

### Supervised green calibration: vertical observation stage

Operator confirmed physical release and suction stopped after corrected OFF.
Added atomic camera observations (session ID, frame sequence, receipt time and
JPEG copied together) and a separate explicit-execution calibration CLI.
The preview restart initially failed to reconnect; a second connection restored
fresh frames. No firmware, address or persistent camera setting was changed.
The first 20 mm upward segment reached its target, then a 0.05 degree planning
guard rejected the reported 0.23 degree wrist deviation. Reconciled the planning
tolerance with the existing 0.3 degree reached-pose tolerance; preserved the
checkpoint and continued vertically in 20 mm segments at 5 mm/s to Z=200 mm.
Controller idle, no faults, manufacturer release I/O verified. Operator offered
to jog to a useful observation view; autonomous movement ended for that handoff.
No XY sampling, calibrated alignment, camera-guided descent or pickup has run.

### Measured XY fit and rejected pickup path

The operator completed a vertical jog into view. Captured a stable marker,
sampled a 20 mm XY square and independent interior points, and returned to the
raised reference. Maximum residual 0.733 px; holdout maximum 0.504 px. A fixed
+5/+5 mm probe followed by five image-guided corrections converged to estimated
0.063 mm model error. No descent or suction was part of this test.
Operator explicitly confirmed the block had stayed in place. Prepared the
single-pick read-only plan, which aborted on IK discontinuity before any motion.
A finer read-only trace confirmed a wrist singularity near low contact height.
Arm remains at observation height, released, no controller faults. A different
continuous contact/observation configuration is needed before pickup.

### Authorized high observation relocation

User: "lets move it so you can grab it". Confirmed current pose matched the
previous observation state. Read-only checks passed for +40 mm base-X at fixed
height, and the hypothetical new descent had no prior wrist discontinuity.
Executed two +20 mm tool-OFF translations, verified final idle/release.
Added a stationary placement reticle to the UI, invalidated the old active fit,
and instructed operator to reposition the block using the guide without a
ruler. Awaiting block placement; no automatic descent or tool activation.

### Guided placement correction and clearance approach

Operator: "okay its on there". Verified fresh marker and unchanged stationary
wrist. Corrected small placement error with two image-based XY moves at the
same observation height. Fresh full approach IK passed without the previous
wrist jump. Descended along fixed XY/orientation, tool OFF, stopping 10 mm above
the old contact floor. Verified idle/release and no faults. Requested physical
cup-centering/gap inspection before contact teaching. No suction/lift attempted.

### First relocated seal/pick, physical confirmation, and faster repeat

Operator estimated 5 mm to suction contact. Searched at 0.5 mm increments with
pump ON and a strict 5 mm maximum, stopping at confirmed seal after 4 mm. The
first output-transition check aborted before motion; a settling check allowed
the next attempt. Completed 10 mm lift/two-second hold/lower/release. Operator
confirmed physical lift and requested return/one repeat at +15% speed.
Returned continuously to the new observation pose, reacquired green, corrected
small XY drift and descended. Attachment timed out; no lift, release verified.
The repeat had incorrectly delayed suction until contact. Restored ON-before-
descent; a further stationary ON readback showed all-low despite SDK ACK. Added
verified ordered individual-output fallback, then completed same-floor repeat:
seal, 10 mm lift at 2.3 mm/s, hold two seconds, lower/release. Final idle and
release I/O verified. No deeper retry or extra cycle. Actual traces local.

### Second speed increase staged during manual setup

Operator requested another +15% while planning to move the block and jog the
camera upward. Implemented a shared cap of 1.3225 (1.15 squared), retaining
read-only defaults and all other gates. New speed not yet tried on hardware.
37 offline tests/Ruff pass. No robot command issued during operator manual
handoff; fresh ready/pose/camera checks remain required for next execution.

### New-location retargeting and return-height completion

Operator returned the wrist to the calibrated observation height and confirmed
clear travel space. Green was roughly 10 cm from the previous pickup spot.
Read-only IK checked transit and candidate descent regions. Small XY probes
measured current image response; transient missing masks exposed an overly
brittle observation check. Replaced immediate missed-frame abort with bounded
five-second acquisition requiring three consecutive fresh stable detections;
ambiguity, staleness and camera-session changes still abort.

Measured response passed fit and independent checks but changed the initial
endpoint estimate. Fresh read-only route previews were made from the measured
response; no pickup coordinate was substituted blindly. Reused those fresh
measurements with live origin/camera checks, then verified image response after
every <=5 mm transit. Net displacement 103.331 mm; 22 corrections, maximum image
response residual 2.363 px; final estimated error 0.233 mm. Actual aligned descent
was checked separately. Sealed, lifted 10 mm, held two seconds, lowered/released.
The operator requested automatic post-cycle return. Added a shared release-gated
vertical return to automatic green workflows, and executed that return now to
the original observation height with XY/wrist unchanged. Final idle/release and
fresh camera detections verified. 48 offline tests and Ruff pass.

User next requested a Pick & Place UI button. Implementation is underway; no
additional physical pickup test is authorized solely for UI verification.

## 2026-10-22 — One-cycle UI and first operator run

Added explicit Pick & Place dispatch, a single-job worker, progress reporting,
duplicate-start rejection, session-bound local profile validation and automatic
camera-height return. Added fake HTTP/job and full-cycle tests: 55 offline tests
pass; Ruff and JavaScript syntax checks pass. Read-only live preflight passed.
Reloaded the dashboard while reusing the camera producer; no startup motion.

The operator clicked the button and reported success. The local trace
`button-pick-20261022T225808.json` independently records attachment feedback,
10 mm lift, two-second hold, lowering, verified release and return to about
266 mm observation height. Job completed at 22:59:23 UTC, about 75 seconds
after dispatch. This run began already aligned; prior CLI moved-block trials
provide separate retargeting evidence. User wants faster development and
better workflow; current speed cap remains unchanged.

Chrome access became available afterward. Read-only Studio inspection confirmed
normal position mode at the returned camera height. Inspected the custom deck
in Chrome and corrected stale sidebar/phase labels. Did not operate Studio jog,
tool or speed controls. Most cycle time is vertical approach and return at the
current travel cap; higher-speed tuning remains a separate supervised change.

## 2026-10-22 — Extend the moved-block corridor

The moved marker was visible but its estimated destination lay outside the
original software limits; no move was sent on that rejected request. The user
provided a tabletop/shelf photo and explicitly authorized extending and testing.
Checked a 3×3 grid and exact estimated target using chained hypothetical IK:
high transit, vertical descent, high return and original start. All passed.
These are sampled kinematic checks, not a measured shelf exclusion volume.
Saved the original profile and added the new corridor as a union locally,
without changing camera identity, expiry, contact depth or speed limits.

Executed one authorized cycle through the updated guarded worker. Local trace
`button-pick-20261022T234428.json`: 23:44:28–23:46:14 UTC; 72.261 mm net XY,
16 correction moves (17 tracking observations), max response residual 2.717 px.
Seal feedback confirmed before the 10 mm lift; two-second hold, lowering,
release outputs/input verified, returned to observation height. No extra pickup.

Added a reusable read-only workspace preview module and tests for union gaps,
chained vertical IK and target-aware UI readiness. 58 offline tests, Ruff and
format checks pass. Restarted dashboard only after completion and idle check;
existing camera producer reused and green/min-area-200 settings restored.

## 2026-10-22 — Empty-tool travel tuning

User requested reducing cycle time. Live image showed the block had moved
outside the checked area; requested restore for comparison while implementing
the change. User replied “there”; live detection confirmed near the previous
verified pickup. Kept contact/loaded scale 1.3225, acceleration, image alignment
and contact bounds unchanged. Added independently capped empty-tool travel
20 mm/s, stopping at floor +15 mm for a slow last 10 mm approach. Verified
release before slow initial retreat to +15 mm, then faster camera-height return.

After dry-run full preflight, ran one explicitly requested faster trial. Local
`button-pick-20261022T234936.json` completed at observation height with verified
release in 47.522 s. One small XY correction, seal at the previous shallow
height, 10 mm lift, two-second hold, lower/release/return. Added monotonic event
and phase durations; future UI completion includes measured total. About 37%
less time than the earlier 75.39 s near-aligned run, not a controlled comparison
with the 105.05 s long-retarget cycle. 62 offline tests pass; Ruff and JS syntax
checks pass. Restarted dashboard only when idle, reused camera producer, restored
green/min-area-200 settings. No extra physical cycle during UI verification.

## 2026-10-23 — Hand puppy, upright view and wrist calibration

Built a local MediaPipe 0.10.35 landmark/gesture adapter with pinned version-1
model/hash; no weights or frames committed. Replaced overlapping OpenCV wheels
with one pinned contrib distribution. Added hand mode, skeleton/palm/gesture
overlay, explicit Start/Stop, browser ownership heartbeat, a bounded worker,
controller lease and pickup exclusion.

Operator identified inverted view and chose a forward-facing demo pose. Rotated
dashboard pixels/overlays 180° while preserving producer/control coordinates.
Browser screenshot verified an upright user and readable labels. A same-frame
comparison later showed native upside-down inference gave None while upright
inference gave Open_Palm; changed model input to upright and mapped outputs
back to sensor pixels.

Live controller reported stopped state 5, normal position mode, enabled/braked
motors, no fault/queue and released suction. Operator explicitly finished jogging
and authorized ready-state transition/calibration. State became idle 2 without
pose movement; local resume record retained. Dashboard process had stopped;
restarted it detached with ignored logging while reusing the camera producer.

Several 2 mm translation experiments rejected weak/noisy scene measurements.
Returns from declared checkpoints were separately rechecked/planned. Switched
the first demo to small wrist turns: clearer angular response and puppy-like
centering with base/shoulder joints fixed. Excluded the moving person, fitted a
projective static-scene warp, acquired settled windows and refreshed per-probe
references. Angular calibration uses a 2 px drift/holdout limit (25 px follow
dead zone); this differs from grasp-position calibration. Both wrist directions
passed; holdout 0.6567 px; return checks 0.7623, 1.3014, 0.5737, 0.4825 px.
Nine sampled angular-bound previews passed. The ignored hand profile is separate
from pickup geometry.

Operator started the first follow session at 00:28 UTC. Live trace showed 17
bounded turns early in the session with fixed base/shoulder and zero faults.
Gesture scores around 0.60 initially prevented starting despite clearly straight
fingers. Prepared a combined Open_Palm >=0.50 + explicit four-finger angle gate,
still requiring three fresh frames; not restarted during the active trial.

The first session ended at its 90-second limit after 37 measured joint-target
turns. Non-follow joints had zero target delta; maximum per-target angular
step about 0.30003° including encoder/rounding differences. Operator reported
“worked kind of,” with choppy/minimal movement and wanted larger fluid base/arm
behavior. This is evidence for a wrist prototype, not completion of the full
puppy-demo objective. Next work: continuous control and base participation,
with a separate checked envelope and explicit controller-mode handoff if needed.

2026-10-22 evening (Claude Code): operator asked for real following with fist
pause and return to the ready pose, and called the prior limits overly
conservative. Committed Codex's palm/smoothing changes (c30d734). Rewrote the
follower as a 50 Hz servo-mode velocity loop on J4/J5 using the existing image
Jacobian; removed the 2 h expiry and the 90 s cap. Tests include a simulated
closed loop with 5-tick camera lag converging within 20 px. Restarted the
dashboard (camera producer reused); readiness reported Ready at state 5.
Not yet run on hardware at the time of this entry.

Hardware result (servo following, cce3f7b): three operator-run sessions at
00:50, 00:53 and 00:58 UTC (about 1, 4.6 and 4 minutes) all ended
returned_to_ready with no faults or tracking errors. Operator: "works much
better now"; recorded the demo video. The one-hand lock (33baf16) was committed
during these sessions and was not loaded yet (dashboard not restarted).

Start-pose moves: operator reported that selecting Color detection did not
move to the pickup start. There was no such move; the arm had been jogged by
hand. Added tab-triggered moves between the two demo start poses. Read-only
preview: controller IK for (290, 20, 265.7) chose J4 -179.5/J6 -179.2, a 238
deg wrist swing from the hand pose; selected the equivalent J6 +180.8 branch
used by validated pickups (FK matches target). Joint path both directions:
max 122 deg (J6), tool tip min z 265.7 mm, radius 227-291 mm, no limits.
Removed the pickup profile's 2 h expiry (it had lapsed at 00:40 UTC).
Dashboard restarted; not yet run on hardware at the time of this entry.

Operator confirmed both tab-triggered start-pose moves on hardware (01:12 UTC,
both landed on target joints). Operator: the arm always uses the same camera;
removed the camera-session ID match from pickup and workspace preview (a random
per-process ID, not a measure of the optics or mount). Resolution still checked.
