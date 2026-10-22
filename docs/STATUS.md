# Current project status

Updated 2026-10-22. Historical connection attempts are preserved in [session history](SESSION_LOG.md).

## Current release handling

After the 10 mm trial, the operator reported the vacuum did not shut off. The manufacturer OFF/release command was resent and left asserted: outputs read [0,1,0,0,0], pickup inputs zero, SDK vacuum off. The prior extra 0.3-second release-output reset was removed from both scripts. Physical pump/release confirmation was requested; the subsequent "okay" did not explicitly describe the pump or block. Do not infer physical release solely from the SDK off state. No further motion was sent after that report.

## Running now

- **Lab Deck:** http://127.0.0.1:8100/ (local laptop only).
- **Camera producer:** http://127.0.0.1:8090/ (local laptop only).
- OAK identifies as OAK-D-PRO-POE, with OV9782 color and two OV9282 mono sensors.
- Color, raw, and YOLOX-Nano modes are operational. YOLO runs on the laptop CPU through OpenCV DNN. Current default is green/cyan color detection.
- UFACTORY SDK 1.18.4 reads Lite 6 firmware v2.8.0, controller state, errors/warnings, tool pose, and joint angles. Observed error/warning codes: 0/0. State is displayed as its raw code.
- Actual addresses/configuration and model weights remain under ignored local/.

## Validation

- Eight offline tests passed: color/noise rejection, red wraparound, white background, YOLO grid geometry/NMS, incompatible export rejection, stale detection handling, invalid settings, and a fake robot verifying only connection/getter/disconnection calls.
- Live HTTP checks: fresh frames in raw, color, and YOLO modes; each stream decoded to 640 x 400. Color mode measured about 9 FPS and YOLO about 6 FPS in one short laptop trial. Rates vary with load and are not guaranteed camera rates.
- Official upstream YOLO image smoke check detected dog, bicycle, and car. The actual lab scene may yield zero candidates.
- Invalid vision settings return 400; attempted motion route returns 404.
- JavaScript/shell syntax, Ruff lint and formatting, and dependency consistency checked.
- Launcher start/shutdown verified: it reuses an existing producer, stops its owned deck child, and leaves the external camera producer fresh. Restarted successfully afterward.
- Browser automation reported no available browser or apps; visual layout and manual browser interaction remain unverified. Live endpoint and image delivery were verified directly.

## Explicit boundaries

The browser deck has no movement endpoint and sends no enable, reset, fault clearing, mode change, or tool commands. Separate supervised scripts have issued the authorized suction tests described below; the first authorized 2 mm upward trial has now completed as recorded below. Operator changes through Studio are separate from our scripts. No camera firmware/network write, continuous recording, cloud inference, or IR emitter control was added. There is no camera-to-robot calibration or lab-part training yet.

## Next

Open the deck in the lab browser, review the layout and mode controls, and follow [the classroom guide](CLASSROOM_GUIDE.md). Document mounting/tool geometry and lighting. See [the roadmap](ROADMAP.md) for calibration and later supervised motion checkpoints. The user explicitly excluded motion from this phase.

## Suction calibration research

Found official camera dimensions, Lite vacuum URDF, UFACTORY OAK mount STEP, and the vendor's OAK/Lite 6 grasping example. The example uses a tuned 55 mm flange-to-grip parameter; the URDF defines a 61 mm local TCP. Neither establishes the actual installed cup geometry. Research and a measured-calibration procedure are documented in CALIBRATION_PLAN.md. No vendor motion demo was executed, no nominal offsets applied, and no robot/camera configuration was changed. Physical mounting confirmation remains pending.

## Supervised single pickup requested — geometry pending

The operator authorized one pickup, two-second hold, and release, and stated they can operate the emergency stop. Read-only inspection confirms a fresh green detection and unchanged robot pose; it does not establish the physical cup location or contact height. No move, enable, suction, or reset was issued. Next prerequisite is verified tool/TCP configuration and measured/taught approach/contact geometry, followed by a bounded supervised cycle. This is missing physical information, not a request for repeated authorization.

## Operator-taught approach pose recorded

The operator manually aligned the suction cup over the block with a slight gap. A fresh getter-only SDK read was saved with timestamp, pose, joint angles, and error/status codes under ignored local/taught_poses/. Error/warning codes were zero. This records an approach observation, not contact height or independently verified TCP geometry. No motion or suction command was sent. Next: operator establishes light contact without compressing/pushing the block, then records a separate contact pose.

## Contact candidate recorded

The operator reported pressing the cup onto the block. A getter-only contact candidate was saved locally: it is 3 mm below the taught approach with unchanged X/Y/orientation. Error/warning codes remained zero. Cup compression/light-contact quality has not been clarified, so the record is not marked verified and no cycle or suction was initiated.

## Light contact and bounded trial preflight

Operator-reported light contact was saved locally at about 2 mm below approach and 1 mm above the earlier compressed contact. A live rich report confirmed configured TCP/base offsets zero, load 0.35 kg with configured center of gravity, position mode, enabled motors, and collision sensitivity 3. These are observed controller settings, not independent tool mass/geometry measurements.

Added a separate default-dry-run taught trial script, with a maximum 2.1 mm vertical lift, 2 mm/s speed, 5 mm/s² acceleration, attachment gating, two-second monitored hold, supported-contact release, and fault-aware recovery behavior. The dashboard still has no motion route. Twelve offline tests and live getter-only preflight passed. Source is prepared for the previously authorized single supervised cycle; no suction or motion was issued during preflight.

## First authorized suction trial — aborted before lift

The script issued suction at the taught light-contact pose. SDK attachment confirmation timed out (return code 41). The attachment gate prevented every motion command. Cleanup released suction and ended the release pulse at the supported contact. A separate getter-only inspection confirmed the pose unchanged, zero error/warning codes, and all tool outputs low. No lift/hold/lower motion occurred. No automatic retry was attempted.

Next diagnostic is operator observation of whether the pump ran/formed a seal, then checking the tool's physical seal and correct feedback mapping. A porous wooden surface, insufficient lip seal, pneumatic/wiring issue, or unsuitable feedback channel are possibilities, not established diagnoses. Actual logs remain under ignored local/trial_logs/.

## Repositioned stationary suction diagnostic

The operator reported an audible pump, an earlier lifted cup edge, and manual repositioning. Fresh readback confirmed approximately 9.5 mm X and 9.2° pitch change, invalidating the earlier taught path. A separate diagnostic applied one two-second suction pulse at the newly inspected stationary pose, with no arm-movement API call.

Outputs confirmed suction on; every sampled default vacuum state was 0 (no pickup feedback), with all three tool inputs also 0. After release, outputs were all low and vacuum state -1 (off). Pose remained stationary. This demonstrates command/output operation, not a successful seal. No lift or additional downward pressure was attempted. Operator again requested a pickup; first resolve cup seating/surface seal and record the new geometry.

Added the commented diagnostic utility and two offline checks covering pulse cleanup without motion and refusal after a changed pose. Diagnostic records remain ignored locally.

## Second explicit pickup request — new contact, same attachment timeout

The operator reported a fully sealed cup and explicitly requested suction/lift. Captured a fresh stationary contact and defined a new 2 mm base-frame +Z target with exactly unchanged X/Y/orientation; old coordinates were not reused. Preflight again passed with unchanged controller settings.

The suction command returned SDK code 41 (attachment timeout), so the guard sent no lift. Cleanup released the tool at contact. Read-only verification confirmed unchanged pose, zero errors/warnings, all tool outputs low, and vacuum state off. Physical seal versus feedback-sensor/wiring behavior remains unresolved; the sensor timeout alone does not establish which is wrong. Further blind retries were stopped.

## First feedback-confirmed upward trial completed

After the operator moved down 5 mm, the new contact differed from the prior light-touch region. Movement preparation was stopped; a stationary diagnostic first confirmed vacuum feedback 1 after about 0.3 seconds and maintained it for the rest of the pulse. It was released before the next step. No extra downward motion was sent.

Captured that verified pose, defined an exactly 2 mm base-Z upward target with unchanged X/Y/orientation, and introduced/tested an explicit release-at-hover variant to avoid commanding a descent into the more compressed contact. Executed one specifically authorized trial: suction confirmed → 2 mm upward motion at 2 mm/s → two-second monitored hold → release at hover and end release pulse. The script completed successfully.

A separate read-only postcheck confirmed the reached hover pose, idle controller, zero error/warning codes, all outputs low, and vacuum off. Physical object clearance/drop was not independently measured by the software; cup compliance may absorb some motion, so operator observation remains important. No vision-to-robot calibration is claimed.

The default supported-contact release behavior is unchanged. Added an offline check for the explicit small-drop variant; existing no-seal and fault behavior checks remain. Trial records/coordinates are retained only locally.

## Ten-millimeter trial and release correction

At the operator's explicit request for more lift, added and offline-tested the fixed pickup10 profile. Its live preflight passed. The controller executed verified clearance → known contact → confirmed suction → 10 mm lift → monitored two-second hold → low release clearance. The operator then reported incomplete vacuum shutoff; completion of the motion sequence did not establish physical release.

Immediately issued the manufacturer OFF/release command without arm movement and left it asserted. Readback: DO0=0, DO1=1, all pickup inputs zero, SDK vacuum -1, no errors. Removed the unvalidated extra low-level reset of DO1 from the trial and diagnostic. Added release output/pickup-input verification and a regression test that rejects completion when release feedback stays asserted. All 18 offline tests and lint pass. No corrected motion trial has been run.

Staged the next fixed-height vision calibration/centering plan in JETMAX_TO_LITE6.md. Camera-to-cup mapping and automatic pickup retries are still not implemented or calibrated.

## Current green calibration checkpoint

The operator confirmed the block released and suction stopped. The arm completed
supervised upward-only observation moves to Z=200 mm, 5 mm/s, suction OFF, and
was verified idle before handing observation positioning to the operator.
The camera feed recovered after a preview restart/reconnect failure.

The new `python -m labdeck.green_calibrate` workflow separates upward positioning,
fixed-height XY sampling, and align-only execution. All motion requires
`--execute`; no calibration stage operates suction or descends. The pure response
math has synthetic axis/sign, norm limit and bad-data tests (21 total offline
tests pass). Hardware sampling and alignment remain UNVALIDATED; there is no
vision-calibrated pickup yet. Calibration records and actual device configuration
remain ignored under `local/`.

## Latest measured result: local XY alignment verified

Operator jogged vertically to a useful observation view at approximately
Z=265.72 mm while preserving taught XY and wrist orientation. Fresh images
showed one stable green marker. The tool stayed in manufacturer OFF/release.
A 20 mm square of known XY samples produced the measured response:

```
image_dx_px =  0.1583 * robot_dx_mm - 1.9628 * robot_dy_mm
image_dy_px = -1.9633 * robot_dx_mm - 0.2128 * robot_dy_mm
```

Maximum fitting residual: 0.733 px; independent interior validation: 0.261,
0.410 and 0.504 px. Condition number: 1.028. A +5/+5 mm offset was corrected
using five bounded visual corrections, ending at an estimated 0.063 mm image
model error. This is not independently measured physical cup accuracy.
The operator confirmed the block stayed at its taught location.

**Pickup remains unvalidated.** Read-only descent planning rejected a wrist
singularity: a finer 2 mm diagnostic showed a predicted >60 degree wrist joint
change near the taught low height. No descent or suction command was executed.
Do not loosen the IK guard to make this pass. Establish a contact/observation
configuration with a continuous joint path, re-teach its cup contact and repeat
XY calibration. The arm is idle at observation height with release I/O verified.

`green_pick` is an explicit, default-read-only single-cycle prototype. It checks
fresh alignment and previews the full descent before any movement; on this
current geometry its preflight correctly aborts. It has no retry or depth
extrapolation. All 23 offline tests and Ruff pass. Browser assets pass syntax and
format checks; native browser visual QA is unavailable in this environment.

A follow-up read-only candidate check suggests relocating the same pickup spot
40 mm along robot-base +X would avoid this singular region (largest predicted
joint increment about 0.50 degrees per 2 mm descent; minimum |J5| about 6.09
degrees). This is a hypothetical IK result, NOT collision clearance or a taught
contact. Operator tabletop-space confirmation and fresh contact teaching are
pending; no relocation or movement to this candidate has occurred.

## Relocation completed; operator block placement pending

User explicitly requested relocating the setup for pickup, after confirming
clear space. The empty wrist translated +40 mm in robot-base X as two 20 mm
segments, 5 mm/s, at unchanged observation height/orientation. Rechecked idle,
no faults, release outputs and pickup input low. No descent or suction command.
The candidate full descent was checked read-only at <=2 mm intervals: largest
predicted joint increment 0.501 degrees and minimum |J5| 6.178 degrees.
This remains a hypothetical descent, not physically taught contact.

`green_relocate` defaults to a read-only plan and requires `--execute` to move.
It archives and invalidates the previous active calibration before translation;
actual records are ignored locally. The UI now shows a yellow CUP AIM marker
from the preserved fixed-height camera/tool geometry, explicitly labeled a
placement guide only. The operator is to slide the block to that guide, remove
their hand and report ready. The arm must remain stationary during placement.
New contact teaching and fresh XY checks are required before pickup. Camera
producer stayed connected throughout; only the dashboard was reloaded.

## New block placed; clearance approach completed

Operator reported the relocated marker was on the guide. Live images confirmed
one stable green candidate, no visible hand in the image. The standalone
`green_teach` workflow corrected the small placement error at observation
height with two small XY moves, ending at estimated 0.363 mm guide error.
The complete new vertical approach passed fresh IK preview (maximum predicted
joint increment 1.221 degrees per <=5 mm sample). Executed bounded vertical
segments to 10 mm ABOVE the historical sealed-contact floor; final approach was
2 mm/s. Arm verified idle and released, no controller faults. No tool activation
or newly taught contact occurred. Operator physical inspection of cup centering
and gap/contact is pending. Do not interpret the historical-floor clearance as
an independently measured cup-to-block gap.

Adjusted SDK wait timeout to distance/speed plus settling allowance so a slow
20 mm move at 2 mm/s cannot time out at the old fixed 8 seconds. Added an offline
fake-SDK regression for this case; all 24 offline tests and Ruff pass.

## Latest result: first relocated pickup and 15% faster repeat completed

After the operator reported the cup centered with about a 5 mm gap, a bounded
0.5 mm-step contact search established three consecutive seal reports after
4 mm descent. The arm lifted 10 mm, held two seconds, lowered to 2 mm clearance
and asserted/verified release. The operator confirmed the block physically
lifted. This established a NEW sealed contact floor; it is shallower than the
historical compressed floor. All measured poses and feedback remain local.

The user explicitly requested return to the observation pose and one repeat,
15% faster and without approach checkpoint pauses. The repeat returned in one
continuous vertical move, reacquired the marker, corrected about 1 mm of XY
error, and performed a continuous high approach. The first repeat changed the
successful suction ordering (ON only after reaching contact) and timed out on
attachment; it released at known contact and did not lift. Restored suction ON
before the final slow approach, retaining the SAME new floor and speed cap.

A subsequent stationary readback exposed another fault: the SDK paired ON call
could ACK while BOTH outputs stayed low. This does not prove a firmware race,
and waiting alone did not correct it. The shared `checked_vacuum` helper now
verifies the paired state and, if needed, applies ordered individual output
writes with readback after each. It clears the opposing line before asserting
the desired line; it preserves an already-ON seal and explicitly reasserts OFF.
Output state remains distinct from independent attachment feedback.

With verified ON outputs before descent, the same-floor repeat sealed, lifted
10 mm at 2.3 mm/s, held two seconds, lowered at 2.3 mm/s and released. High
approach/return was 5.75 mm/s; final search was 0.575 mm/s. Accelerations, contact
floor, seal gates and two-second hold were unchanged. Final robot state idle,
no faults, release pair [0,1] and pickup input low. No automatic extra cycle.

This is a supervised LOCAL green-guided pickup prototype, using the measured
fixed-height response and a newly verified cup/contact anchor. It is not a
workspace-wide calibration or unrestricted gesture policy. The old active fit
remains invalidated after relocation; source records and trial traces preserve
the distinction. All 34 offline tests pass, including failed seal/no lift,
output ACK/both-low repair, output readback failure, timeout coverage, and the
15% speed cap. Ruff and browser syntax checks pass.

## Next test staged: second 15% speed increase, manual handoff pending

Operator plans to raise the wrist manually back to observation height and move
the block a few millimeters for a new-location test. They explicitly authorized
another 15% speed increase. Compounding the earlier 1.15 yields 1.3225 relative
to the original rates: travel 6.6125 mm/s, lift/lower 2.645 mm/s, final contact
search 0.66125 mm/s. These rates are STAGED, not yet hardware-tested.

A shared finite-number validator now enforces the 1.3225 cap in the repeat CLI,
contact search, and pick cycle. Defaults remain read-only and scale 1.0; the
next authorized test will explicitly select 1.3225. Acceleration, contact floor,
seal/release gates, two-second hold and spatial limits are unchanged. All 37
offline tests pass, including the new rate's unchanged path, no-lift-on-failed-
seal behavior and rejection of nonfinite/above-cap values.

No robot commands were sent for this update. Wait for operator ready after the
manual jog/placement, then verify fresh pose, camera context and new target.
The prior completed-trial state is not permission to replay an old log or
bypass the manual-handoff checks.
