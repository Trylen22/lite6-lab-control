# Project instructions

## Scope and classroom purpose

All Lite 6/OAK work belongs in this repo. Do not modify the sibling JETMAX repo
or borrow its device addresses, poses, camera offsets or motion limits. Keep
modules focused, heavily commented and educational: explain units, coordinate
frames, SDK return codes, concurrency and failure handling. Never label pixels
as robot targets without explaining the calibration and its domain.

## Hardware authorization and current state

The operator is present in the lab with the physical E-stop reachable. Mounting,
controller-reported tool/load settings and supervised low-speed trials were
established in this session. User authorized green-guided pickup development,
bounded trials, two compounded 15% increases for contact/loaded motion (maximum scale 1.3225), and
return to observation height after every successful cycle. A moved-block test
tracked about 103 mm, sealed/lifted/placed/released, and returned to camera height.
See docs/STATUS.md and docs/SESSION_LOG.md for evidence and remaining limits.

The latest request explicitly covers adding a Pick & Place UI button. Each click
may authorize ONE complete guarded cycle. Do not start motion on page load,
server startup, failed detection, or an automatic repeat loop. Do not send a
new physical test merely to test the button unless the user requests that run.
Manual operator jogging/placement handoffs prohibit overlapping agent movement;
re-read pose, tool outputs, controller state and camera context after a handoff.

## Nonnegotiable controller boundaries

Start with fresh read-only status. Do not enable motors, release brakes, reset
faults, change modes/offsets/load, flash firmware, configure startup or change
network settings without a concrete request covering that operation. Do not
clear a stopped state merely to make a script pass. Reject unknown configurations.

Use the new shallow seal reference, never the old deeply compressed contact.
Keep the inspected fixed height/orientation/tabletop domain and checked travel
bounds. Preview IK continuity/joint limits; IK does not prove obstacle clearance.
Suction must be ON/output-verified before final search and independently sealed
before lift. SDK paired writes can ACK yet leave both outputs low: use the checked
suction helper. OFF/release is DO0=0, DO1=1; leave it asserted and verify input low.
Return vertically only after release verification. Faults, lost targets, failed
seal or uncertain pose never authorize deeper contact or blind recovery.
Preserve the physical E-stop distinction from software UI controls.

## Configuration and version control

Actual device settings, poses, workspace profiles, weights and traces belong in
ignored local/; commit sanitized examples. Keep credentials and secrets out of
source/remote URLs. Pin confirmed dependencies. Record validation and limitations
in docs/STATUS.md, preserve detailed history in docs/SESSION_LOG.md, and maintain
the classroom guide/architecture. Review staged content, commit and push completed
work to the existing private repo as requested. Verify the remote before claiming
a successful push.

The Pick & Place UI is implemented. Its first operator-triggered hardware cycle
passed, including release and camera-height return. Keep local automation profiles
ignored and session-bound. Preserve single-job dispatch and full per-click
preflight when extending the interface.

The operator authorized and one trial validated an additional moved-block
corridor. Profile regions are a union; do not replace them with the entire outer
rectangle. Chained predicted travel/descent/return preview precedes movement,
and actual aligned descent is checked again. Sampled IK is not shelf collision
detection. Latest test: 72.26 mm net XY, seal/lift/release/return passed at the
unchanged speed cap. See STATUS for scope; no additional pickup is implied.

The subsequent explicit speed-tuning request authorized separate empty-tool
travel. One supervised cycle passed at 20 mm/s above floor +15 mm; slow final
approach/initial retreat and all contact/alignment/loaded speeds remain unchanged.
The local profile selects that rate; old profiles retain legacy speed. Trial
total 47.52 s (near-aligned start). Do not apply this rate to loaded/contact
motion or raise the 20 mm/s cap without a concrete new speed-tuning request.

Hand puppy work is authorized. On 2026-10-22 the operator replaced the
wrist-step prototype ("choppy/minimal") with continuous following: xArm servo
mode (mode 1) streams J4/J5 targets at 50 Hz, <=20 deg/s, <=80 deg/s^2, within
+-30/+-25 deg of the pose at Start (hand_servo.py, hand_follow.py). Open palm
follows, fist glides back to that ready pose, no hand holds then homes after
3 s, Stop/heartbeat loss homes and restores position mode + ready state.
Start may resume a software-stopped arm (state 5); it never clears faults.
The hand calibration no longer expires (camera-mount geometry, not time);
start is refused >15 deg from the calibrated anchor. Base/shoulder/elbow/roll
stay fixed and suction stays released. `local/hand-follow.json` stays ignored.
Do not restart the dashboard during an active follow session.

Demo start poses (2026-10-22, operator request): clicking the Color detection
tab moves the arm to the pickup start; clicking Hand puppy moves it to the
hand-demo anchor (labdeck/start_pose.py). One joint move at 25 deg/s after an
FK-sampled path check (tool tip >= 250 mm, no joint limits). Pickup start
joints live in ignored local/start-poses.json on the validated wrist branch
(J4 ~ -180, J6 ~ +180); the controller's own IK branch spun the wrist ~238 deg.
Page load and status polling still never move the arm. The pickup profile no
longer expires, and a restarted camera program (new session ID) does not
require recalibration: same camera and mount. Resolution is still checked.

Pickup workspace widened (2026-10-23, operator decision): the operator said
the tabletop is large and only ~1 ft to the side risks the table, overriding
the earlier "union, never the outer rectangle" rule. A read-only IK sweep
(X 230-390 step 20, Y -180..180 step 30, high -> contact floor -> high ->
start) passed everywhere with X >= 250. local/automation.json now uses one
region X 250-390, Y -170..180 (about the camera's view); the old regions are
kept in "previous_xy_regions_mm" and local/automation.before-widen-*.json.
