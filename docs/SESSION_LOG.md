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
