# Calibrating vision to the suction cup

Status: reference research and procedure only. No calibration transform is fitted, no controller settings are changed, and no robot motion is authorized by this document. The installed tool and mounting arrangement still need physical confirmation.

## The two relationships we need

1. **Tool center point (TCP):** the suction cup's contact center relative to the robot's tool flange. The soft cup lip, adapter plates, and mounting orientation affect this measurement.
2. **Camera extrinsics:** the color camera's optical frame relative to the flange (wrist-mounted camera), or relative to the robot base (fixed camera).

The camera's housing length does not establish either relationship. Camera intrinsics describe projection inside the camera; they do not tell us where a third-party bracket mounts it on the robot.

## Official reference geometry found

These numbers describe manufacturer reference setups. They are NOT our measured calibration and are deliberately absent from active device configuration.

| Reference | Published value | How to use it |
|---|---|---|
| Luxonis OAK-D Pro PoE product dimensions | 111 × 40 × 31.3 mm | Check enclosure and bracket identity; this is not a camera-to-cup offset. Confirm the actual revision and installed connectors. |
| UFACTORY Lite vacuum URDF | `joint_tcp` at `[0, 0, 0.061]` meters from `uflite_vacuum_gripper_link` | Nominal 61 mm along that model's local Z. The attachment transform must also be considered before calling this a flange offset. |
| UFACTORY OAK + Lite 6 grasping example | `GRIPPER_Z_MM = 55` | The example describes a flange-to-gripping-point distance and explicitly requires tuning to the actual setup. Do not average this with the URDF value. |
| Same OAK example, reference camera mount | Source Euler vector `[0.0703, 0.0023, 0.0195, 0, 0, 1.579]`, meters/radians | A reference end-effector-to-color-optical transform for the author's mount. Confirm its frame/convention and exact bracket before using even as an initial estimate. |

The 55 mm demo parameter and 61 mm model TCP show why we need to identify and measure the actual tool. They may reflect differing reference geometry, contact conditions, or versions; the sources do not establish which applies here. The generic xArm vacuum preset is not automatically a Lite vacuum-tool calibration.

Official sources:

- [Luxonis OAK-D Pro PoE dimensions and variants](https://checkout.luxonis.com/products/oak-d-pro-poe)
- [UFACTORY Lite vacuum-gripper URDF](https://github.com/xArm-Developer/xarm_ros2/blob/humble/xarm_description/urdf/vacuum_gripper/lite_vacuum_gripper.urdf.xacro)
- [UFACTORY OAK + Lite 6 example parameters](https://github.com/xArm-Developer/ufactory_vision/blob/main/ggcnn_grasping_demo/example/luxonis_oak_poe/run_oak_poe_grasp_lite6.py)
- [OAK example setup and camera-stand download](https://github.com/xArm-Developer/ufactory_vision/blob/main/ggcnn_grasping_demo/example/luxonis_oak_poe/README.md)
- [Official camera-stand STEP archive](https://www.ufactory.cc/wp-content/uploads/2025/12/oak_camera_stand.zip)
- [Luxonis enclosure/PCBA CAD links](https://github.com/luxonis/oak-hardware/tree/master/NG9097_OAK-D-Pro-PoE/Mechanical)

Reference files were downloaded only to ignored `local/` for inspection. The camera-stand archive contains `oak_camera_stand_2.STEP`. The grasping demo was read as source and was NOT executed: running it would introduce robot motion and assumptions outside this phase.

## Recommended measurement sequence

### A. Identify the installation without moving it

Photograph the camera, bracket, flange, adapter, and suction cup from the side and front, ideally with a ruler. Record the tool model, cup dimensions, and whether the camera is attached to the wrist or fixed separately. Compare with the official CAD instead of assuming the manufacturer's example mount is installed.

Measure the rigid offsets from known mounting surfaces to the cup's contact center. Distinguish an uncompressed lip from the light-contact position. Do not treat the published enclosure size or stereo sensor spacing as the color optical center's offset to the cup.

Read the controller's currently configured TCP/base offsets before interpreting poses. The current observation loop's getter-only pose display does not independently validate these settings. SDK cached properties must not be reported as actual offsets unless a valid report has populated them. No settings should be overwritten just to match a vendor demo.

### B. Read camera calibration and preserve the image geometry

Read factory intrinsics/distortion for the actual color sensor through the process that owns the camera; avoid opening a competing device connection. Record sensor identity, output size, crop/resize/undistortion mode, and calibration version.

Our current image is 640 × 400 from CAM_A. Calibration must describe that image geometry. A transform fitted to a cropped/resized/rotated picture cannot be blindly applied to another output. Stereo depth also needs validated alignment to this color image if used for target position.

### C. Calibrate the actual cup TCP (future supervised measurements)

After explicit motion authorization and the physical preparation described in the roadmap, use the controller's supported TCP calibration procedure or a carefully measured fixture. A compliant suction cup can be harder to use as a pivot tool than a rigid tip; choose a method that does not deform the cup or rely on pushing it into a point.

Record the flange-to-cup transform, reference surfaces, units, contact definition, and repeatability. Validate that the physical contact center matches the reported TCP at several orientations. Account for the already configured controller TCP exactly once; do not add the cup length twice.

### D. Calibrate the camera-to-robot relationship

- **Wrist-mounted camera:** use a measured checkerboard/ChArUco target fixed in the workspace and collect synchronized robot flange poses plus camera target poses at multiple sufficiently varied positions/orientations. Solve an eye-in-hand transform, for example with OpenCV's `calibrateHandEye`. This requires future supervised arm movement; no movement is part of the current research step.
- **Fixed camera:** solve an eye-to-base arrangement using measured base-frame target coordinates or a suitable eye-to-hand procedure. The transform does not move with the wrist.
- **First flat-block experiment:** a planar mapping can be a simpler teaching stage if the observation camera pose and object-top plane remain fixed and are measured. If the camera is wrist-mounted, a single image-to-table homography is valid only at the calibrated observation pose; it must not be reused after moving the wrist. A changed block height also changes the mapping unless explicitly modeled.

For a wrist camera, define `T_A_B` to map coordinates expressed in frame B into frame A:

```text
p_base = T_base_flange × T_flange_camera × p_camera
T_base_cup = T_base_flange × T_flange_cup
```

These equations identify frames; they are not movement commands. Converting an observed 3D point into a complete cup pose still requires a defined orientation, contact height, approach path, and validation. A single 2D pixel does not determine a unique 3D point without depth or a known plane.

[OpenCV hand-eye calibration reference](https://docs.opencv.org/5.0/main_modules/calib.html)

### E. Validate before implementing a pickup

Use reference points not used in fitting, distributed through the intended working region. Measure lateral and height error separately; include lighting, image timing, tool compliance, and object height in the uncertainty discussion. Set tolerances from the cup's usable contact area and the actual object geometry.

Start with a dry-run overlay and compare predicted versus measured points. Future supervised hover checks should precede descent. No real robot target should be generated from an unvalidated nominal CAD transform.

## Current missing information

- Wrist-mounted or fixed camera, exact bracket, and its attachment orientation.
- Exact vacuum tool, adapters, and installed cup/contact geometry.
- Valid reported controller TCP/base offsets.
- Factory camera calibration tied to the active 640 × 400 image geometry.
- A measured reference target/plane and independent validation observations.

No active calibration file or controller offsets were populated from the reference dimensions.

## Implemented fixed-height experiment

`python -m labdeck.green_calibrate raise --z HEIGHT` previews only; adding
`--execute` requests upward-only movement through short checkpoints. It requires
the local historical contact record and the verified released starting pose.
`sample` measures a 20 mm XY square at one height and wrist orientation, fits
`pixels = aim + J * robot_XY_displacement`, and checks separate interior samples.
`align` solves `J * correction = aim - current_pixels`, damps the result, caps
each step at 2 mm, and refuses positions outside that measured square. Sampling
and alignment remain physical experiments pending validation.

The camera process supplies an atomic observation with a producer session and
frame sequence. Calibration requires three distinct fresh, stable frames and
exactly one candidate; it does not select the largest among ambiguous targets.
A camera restart invalidates a fitted model. Height, orientation, image geometry,
controller offsets, load, release I/O and controller health are checked.
IK samples test reachability and joint continuity only; they do not establish
obstacle clearance. Scripts never enable/reset the arm or recover blindly.

The aim point is meaningful only when the raised pose retains the XY relationship
of the successful cup contact AND the block has not moved. Dropping a block may
shift it; that relationship must be physically checked before descent. A good
least-squares residual alone cannot prove the cup will contact the marker.
There is no descent, tool activation or unlimited retry in this experiment.

### Operator jog and path checks

After a vertical operator jog, `adopt-watch` records a fresh useful view only if
XY and wrist orientation match the preceding reference. It never moves hardware.
`probe --execute` makes one fixed +5/+5 mm offset for a feedback test; follow
with `align --execute`. Keep the block still during sampling/probing. An actual
block move needs a new fresh observation, valid sampled region and scene check.

`python -m labdeck.green_pick --block-unchanged` prints the single-pick plan and
checks the whole descent without moving. The extra flag records the operator's
physical confirmation, not a vision inference. `--execute` is deliberately
separate. The current taught path is rejected at read-only preflight because
of wrist IK discontinuity. Do not execute until the geometry is re-taught and
planning passes; do not increase thresholds to hide a singularity. A straight
TCP path can still require a large joint rotation.

### Relocating an observation spot without a ruler

`python -m labdeck.green_relocate` plans a specific +40 mm base-X relocation;
`--execute` runs two slow high-level checkpoints with the tool OFF. This is a
supervised installation experiment, not a general arbitrary jogging interface.
It first previews translation and hypothetical descent, archives/invalidate the
old active fit, then records each completed checkpoint. Failures never trigger
a recovery move. The UI's yellow CUP AIM retains the fixed camera/tool image
geometry during pure XY translation and guides manual block placement. It does
not certify contact or preserve the old fit's sampled workspace. New contact
teaching and measurements must establish the relocated pickup region.
