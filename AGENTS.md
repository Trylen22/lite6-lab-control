# Project instructions

## Fresh-clone and new-session entry point

Read `docs/AGENT_SETUP.md` and `docs/LAB_SETUP.md` before setup work. Known
station network addresses are published in `config/lab.station.example.toml`;
runtime settings and measured motion profiles remain in ignored `local/`.
Use `config/lab.simulator.example.toml` and `/#lab` for a fresh-clone Lab preview.
Historical statements below about an operator being present and movement being
authorized describe the original supervised development session. Do not infer
that those conditions hold for a new collaborator or a later session.

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

Runtime device settings, poses, workspace profiles, weights and traces belong in
ignored local/; the shared station network example is deliberately published.
Commit sanitized examples for other settings. Keep credentials and secrets out of
source/remote URLs. Pin confirmed dependencies. Record validation and limitations
in docs/STATUS.md, preserve detailed history in docs/SESSION_LOG.md, and maintain
the classroom guide/architecture. Review staged content, commit and push completed
work to the existing project remote as requested. Verify the remote before claiming
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
Start may resume a software-stopped arm (state 5) and, since 2026-10-28 at the
operator's request, enable the motors of a powered-up arm (state 4 with error
codes [0, 0]) on a demo click or Start; it never clears faults.
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

Pickup speed (2026-10-23, operator: a 52 mm pick took 69 s, "snail speed"):
the button cycle now uses the faster profile in motion_profile.py. Empty-tool
travel 60 mm/s at 200 mm/s^2 (alignment, approach to floor+15, return);
final 10 mm in/out 10 mm/s; contact steps still 0.5 mm with the 3-read seal
check, at 2.5 mm/s; loaded 10 mm lift/lower 10 mm/s; monitored hold 0.5 s.
Alignment takes one large step (90% of error, <=60 mm) then corrections.
Other scripts keep their old defaults. This supersedes the 20 mm/s cap note.

Pick -> Shelf (2026-10-23, operator request and hand-traced path): the deck's
second button picks the green block and carries it to the shelf drop zone
(labdeck/shelf_place.py, waypoints in ignored local/shelf-place.json from
local/taught_poses/shelf-path-*.jsonl). Order is fixed: 10 mm lift + seal hold,
straight up to camera height, rise with the BASE LOCKED, base-only level turn,
short reach/tilt, release, then the reverse. Waypoints were re-solved onto the
pickup wrist branch. Start-pose moves now refuse a base swing > 30 deg or a
wrist turn > 150 deg (e.g. from the shelf, or a hand-jogged wrist branch).

Lab tab (2026-10-23, operator request): Blockly (Studio-compatible blocks) on
the left, a simulated Lite 6 (three.js + UFACTORY xarm_ros2 meshes) on the
right. SIMULATION ONLY: assets/lab/* never sends robot commands; it only reads
telemetry to copy the arm's pose into the sim. Imports/exports Studio .tar.gz
projects. Kinematics are fitted per arm to the controller's own FK
(scripts/fit_lab_kinematics.py → ignored local/lab-kinematics.json, 0.38 mm).
Running student programs on the real arm would be a separate, guarded feature.
