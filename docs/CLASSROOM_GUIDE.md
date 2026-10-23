# A first session with the Lab Deck

These exercises observe the setup. They do not require robot motion. Keep objects and hands clear of the robot's mechanisms, and use the lab's operating arrangements.

## Learning goals

By the end of this phase, a student should be able to:

- Trace a camera image through a Python worker to a browser.
- Explain BGR versus HSV, a threshold mask, morphology, contours, and centroids.
- Distinguish a color match from a learned object class.
- Explain a bounding box, image coordinates, and YOLO duplicate suppression.
- Read SDK return codes without confusing observations with commands.
- Explain why a 2D detection is not yet a robot pickup location.

## 1. Connect the observations to the code

Open the deck and compare **Vision workspace**, **Robot telemetry**, and **System notes**. Locate the corresponding source files in the source map.

Questions:

1. Which process directly owns the OAK device?
2. Which process receives the arm's telemetry?
3. What happens if the browser is closed? The local workers continue until stopped.
4. What would have to change for a second computer to access this loopback-only page?

Read the comments in `scripts/run_lab.py` before starting or stopping a session. Explain why an externally started producer is reused rather than terminated by the launcher.

## 2. Raw pixels and a threshold mask

Select **Raw camera**, then **Color detection**. Place a green or cyan object in the camera's view without moving the arm. Select **Show threshold mask**.

Read `labdeck/color.py` alongside the screen:

1. Identify the HSV threshold values shown in the interface.
2. Find white regions in the mask and compare them with the raw image.
3. Raise the minimum area. Record which small regions disappear and which persist.
4. Try another preset. Explain why the red preset has two HSV intervals.
5. Observe a similarly colored distractor. Explain why color matching cannot determine the object's identity.

Expected observations depend on lighting and the scene. An empty result can be correct. Never lower a threshold just to make a demonstration look successful without explaining the tradeoff.

## 3. Coordinates have meanings

Inspect a detected color region. The table shows its centroid and area. The origin is the top-left image corner; X increases rightward and Y downward.

- What image region does the bounding box describe?
- Why does the area change if an object appears larger in the camera?
- Why can't a centroid such as `(320, 200)` be sent directly to the arm?
- How would camera mounting and object height affect a pixel-to-robot conversion?

No millimeter scale is assumed by this detector. Use `docs/ROADMAP.md` to discuss the measurements needed for a calibrated pick.

## 4. Compare with YOLO

Select **YOLO objects**. Introduce an everyday COCO object such as a cup, bottle, or keyboard where it is visible to the camera. Do not expect this small pretrained model to recognize arbitrary bolts, special grippers, or colored lab blocks.

Read `labdeck/yolo.py` in this order:

1. Letterbox preprocessing and its scale ratio.
2. Model inference through OpenCV DNN.
3. Grid/stride decoding into box centers and sizes.
4. Objectness × class score and confidence filtering.
5. Non-maximum suppression and mapping into original-image pixels.

Increase confidence and note the effect on candidates. Record one missed object or false positive. Compare YOLO and color detection on the same scene: what information does each method provide?

The camera can run compatible neural networks on its own processor, but this lesson deliberately runs YOLO locally so the full path is inspectable. Later optimization should preserve these lessons and validation cases.

## 5. Read robot status without changing it

Open **Robot telemetry** and inspect `labdeck/robot.py`.

- List every SDK method called by the observer.
- Distinguish a getter's return code from the controller state code in its returned value.
- Explain the millimeter and degree units.
- Why does the interface display only six joints when the SDK can return seven values?
- Why do error and warning codes of zero not prove that a robot is safe to move?

The observer has no enable, clear-error, reset, home, jog or gripper command. The separate Pick & Place button is outside this observation lesson; it dispatches a guarded worker only after an explicit click.

## 6. Test a failure safely

Prefer an offline test or stopping the local camera producer over changing hardware wiring. Coordinate process changes with the instructor and restore the producer afterward.

Observe how the stale overlay, detection list, and connection indicators behave when fresh images stop. A frozen image must not be interpreted as a current target.

Run the offline tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Read each test's scene and expected outcome. The synthetic scenes verify color/geometry properties without depending on a particular lab image or moving hardware. The fake robot verifies the getter-only boundary without a physical device.

## Suggested lab notes

Record the hypothesis, settings, lighting conditions, expected behavior, actual behavior, and one limitation for each experiment. Save diagnostic images locally only when authorized; they are excluded from Git by default. Commit source and sanitized educational notes, with validation clearly distinguished from untested plans.

## Lesson: retargeting a moved block

The successful new-location experiment moved the wrist about 103 mm using image
feedback, without manually teaching the new block location. Keep the observation
height and wrist angle fixed. Measure the 2x2 response J, then solve
`J * XY_correction = cup_aim_pixel - marker_pixel`. A fitted intercept locates the
marker at the measurement origin; it is NOT automatically the cup's aim pixel.
The aim has separate provenance from a position that actually sealed and lifted.

Check a separate measurement point and compare predicted versus observed image
movement at every short step. A destination estimate helps preview the transit
region; the final aligned vertical approach gets its own fresh IK check. Stay
within the tabletop/contact-height domain. Camera alignment and suction contact
are separate checks. A missing mask resets the consecutive-frame window; three
new stable detections are still required. Never reuse stale centroids to keep a
robot moving. After seal-gated pickup and verified release, finish at observation
height so the next block placement can be seen.

Class exercise: explain why a single retargeting success differs from demonstrated
repeatability across several positions, and why low image-fit residual alone
cannot prove physical cup accuracy or obstacle clearance.

## Lesson: from a button to one controlled cycle

Read `assets/app.js`, `labdeck/server.py`, `labdeck/jobs.py`, then
`labdeck/automatic_pick.py`. Trace a click through validation, the single-job lock,
preflight, alignment, seal, lift, release and camera-height return. Explain why
GET status requests cannot start movement, why two clicks must not create two
workers, and why a camera-session change invalidates the local profile.

Use fake-worker tests to explore failures without moving hardware. Distinguish
UI readiness from the worker's fresh hardware checks. The first real button
cycle passed; that single result does not establish repeatability everywhere.

## Lesson: workspace limits versus physical obstacles

A color target can be visible while its estimated pickup position lies outside
the accepted region. Explain why a large empty tabletop does not automatically
provide reachable poses, shelf clearance or a valid image mapping. Compare the
outer bounding rectangle with a union of checked corridors.

Read `workspace_preview.py` and `test_workspace_paths.py`. Why must a predicted
vertical descent be checked after the hypothetical high transit? What does the
3×3 grid establish, and what still requires operator inspection and physical
trials? Contrast estimated image error with independently measured cup accuracy.

## Lesson: make a cycle faster without speeding every phase

Inspect `clear_travel_speed` and the staged approach/retreat in
`automatic_pick.py`. Which movements carry the block? Which happen near contact?
Why should one global speed multiplier not control all of them? Compare
`phase_seconds` across similar runs and explain why travel speed, acceleration,
frame acquisition, IK checks, seal confirmation and deliberate hold all affect
the total. A speed command is not a promise of constant achieved speed.

## Lesson: the hand-follow feedback loop

Read `hands.py` (model output), `display.py` (display-only image transform),
`hand_space.py` (separate wrist bounds), and `hand_follow.py` (intent and policy).
Why must the UI's 180° view rotation leave controller pixels unchanged? Why is
a changed wrist pose different from a changed display?

Trace one Start request and browser heartbeat through three fresh open-palm
frames, smoothing, dead zone, bounded correction, IK and a final intent check.
Use `test_hand_follow.py` and `test_hand_follow_http.py` to explore a fist,
multiple hands, camera restart, stale frame, lost heartbeat, boundary, stop
during planning and pickup conflict. No physical hardware is used in those tests.

Hand calibration uses static-scene optical flow. A camera turn produces a
projective image warp. Compare a median off-center flow with a fitted spatial
warp evaluated at the image center; neither yields measured hand depth.
Discuss what the independent holdout and return-to-origin checks establish
and why an image fit alone cannot establish clearance around a person.
