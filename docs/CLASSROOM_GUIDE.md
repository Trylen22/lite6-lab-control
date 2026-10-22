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

No millimeter scale is assumed by this detector. Use `docs/ROADMAP.md` to discuss the measurements needed before any future pick.

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

There is no enable, clear-error, reset, home, jog, pick, or gripper button. No physical motion is part of this lesson.

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
