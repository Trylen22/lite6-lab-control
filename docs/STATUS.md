# Current project status

Updated 2026-10-22. Detailed trial history is in [SESSION_LOG.md](SESSION_LOG.md).

## Demonstrated on hardware

- OAK color video and green-marker detection; CPU YOLOX-Nano also available.
- Fixed-height, fixed-wrist XY image-response calibration and independent checks.
- Suction output readback plus independent seal feedback before every lift.
- A moved-block test tracked **103.33 mm** from the starting observation pose,
  aligned using 22 bounded corrections, sealed, lifted 10 mm, held two seconds,
  lowered and verified release. No manual contact teaching at the new location.
- The final estimated image-model correction was 0.233 mm; this is not an
  independently measured physical cup-position error. Maximum per-step image
  response residual was 2.363 px, below the 3 px consistency limit.
- After the operator requested a complete return, the empty wrist moved straight
  up to the original observation height (about 266 mm), preserving XY and wrist.
  Idle state, zero faults and release I/O were verified.

## Current workflow and bounds

The tool stays OFF during observation/alignment/high approach. Suction is enabled
and its output state verified BEFORE the final 5 mm bounded search. Seal feedback
must be stable before the 10 mm lift. Release is DO0 low / DO1 high and is left
asserted. Completed automatic green cycles now return vertically to observation
height after verified release. Failures never authorize a deeper contact, blind
recovery movement, or automatic extra cycle.

The demonstrated domain is the same tabletop, same block height, camera session,
observation height and wrist orientation, within explicitly checked travel
regions. It is not arbitrary 3D calibration, a table-wide guarantee, or a gesture
policy. The preserved cup image anchor and latest shallow sealed-contact floor
are distinct from old deeply compressed trial poses; never substitute the latter.
All actual configuration, regions, reference poses and traces remain ignored in
`local/`. The old active fit was invalidated after relocation; experimental
retargeting records retain their measured response and contact provenance.

Current contact/alignment speed scale is **1.3225**: two compounded 15% increases.
Alignment and near-contact travel 6.6125 mm/s, lift/lower 2.645 mm/s, final search
0.66125 mm/s. Subsequent empty-tool speed tuning is recorded below.
Accelerations and the two-second hold are unchanged.

## Software checks

62 offline tests pass. Coverage includes frame freshness/session identity,
duplicate-frame rejection, consecutive stable detection after missed frames,
ambiguous-target rejection, calibration math, corridor bounds, seal-before-lift,
verified output transitions, speed limits and release-gated vertical return.
Ruff lint/format and browser JavaScript syntax checks pass. Live HTTP, image delivery, dispatch rejection and duplicate-job behavior were verified.
Chrome inspection confirmed the live controls and completion status; corrected a
stale sidebar label that incorrectly claimed motion was unavailable.
The operator subsequently confirmed the first real UI-triggered pickup worked;
its trace verifies seal, 10 mm lift, hold, release and return to observation height.

## Running services

- [Lab Deck](http://127.0.0.1:8100/) and [camera producer](http://127.0.0.1:8090/).
- The producer owns the OAK connection. Dashboard reloads reuse that connection.
- Device addresses, controller setup, model weights and trial records stay local.

## Pick & Place button

The button is live and the first operator-triggered cycle passed on hardware
(22:58:08–22:59:23 UTC, about 75 seconds). It starts one complete guarded cycle
through a separate worker, reports progress and prevents duplicate starts.
Opening or restarting the dashboard never starts movement. The current local
profile expires and is tied to the camera session and checked tabletop region.
Speed and broader repeatability still need further supervised development.

## Workspace extension — 23:46 UTC

The next block placement initially failed the original software XY bounds
before movement. The operator identified clear tabletop space and a nearby
shelf, then authorized a checked extension. Nine getter-only grid previews
passed for high transit, vertical descent and return. The profile now keeps
the original region plus a new corridor as a union, rather than admitting
the entire outer rectangle. Shelf geometry was not measured or automatically
detected; clearance depends on the operator's inspection of the full swept
arm/camera space.

One supervised cycle then passed: 72.26 mm net XY travel, 16 bounded correction
moves, maximum image-response residual 2.717 px, stable attachment feedback,
10 mm lift, two-second hold, verified release and return to observation height.
It took about 105 seconds with the unchanged speed cap. This demonstrates the
new placement, not full coverage of the sampled corridor or entire tabletop.

Added initial chained transit/descent/return preview, per-segment region checks
and cached-target readiness. The worker still checks the actual aligned descent.
Restarted only the dashboard after completion, reused the camera session and
restored the green detection threshold. Actual geometry and traces stay local.

## Separate clear-travel tuning — 23:50 UTC

User authorized reducing cycle time and restored the block near the successful
pickup location. Added a separate 20 mm/s empty-tool rate above floor +15 mm.
Final approach and initial release-gated retreat retain 6.6125 mm/s. Image
alignment, 0.5 mm contact increments, depth floor, seal confirmation, loaded
lift/lower, hold and acceleration remain unchanged.

One supervised trial passed in **47.52 s**, including one small alignment move,
seal feedback, 10 mm lift, two-second hold, release and camera-height return.
Phase timings: approach 12.14 s, search/seal 10.50 s, lift 4.36 s, hold 2.04 s,
lower 3.81 s, return 12.35 s; remaining time is checks/vision/alignment.
This is about 37% shorter than the earlier 75.39 s near-aligned UI cycle, with
slightly different placement/contact. The 105.05 s long-retarget trial includes
additional alignment work and is not a controlled speed comparison.

Added monotonic event/phase durations and completion time in UI job messages.
62 offline tests pass, including fast/slow phase separation and failed-seal
behavior. Dashboard reloaded after idle verification; camera session reused.
No second faster pickup was issued.

## Hand puppy development — 2026-10-23 UTC

The operator chose a forward-facing wrist pose for the demo. It differs from
the pickup pose, so tabletop XY motion is correctly unavailable there. The
operator explicitly authorized resuming the stopped controller at that pose;
read-only checks found six enabled/braked motors, no queued commands or faults,
and released suction. Ready-state transition left the pose unchanged.

Added local MediaPipe landmarks/gestures and an upright dashboard image. The
model also receives upright pixels; its landmarks are mapped back to native
sensor coordinates before controller math. This fixes gesture recognition
without silently changing calibrated image directions.

Tiny translational scene probes were too weak/inconsistent for this view. The
first puppy demo instead uses wrist joints 4/5; base/shoulder/wrist-roll joints
stay fixed. One supervised wrist calibration passed both directions, returned
to its encoder anchor and passed an independent holdout at **0.657 px**. Maximum
image return drift was 1.301 px, within the 2 px angular-centering criterion.
A 3×3 wrist-range preview passed joint limits and sampled FK displacement.
This is a separate expiring profile; pickup calibration was not overwritten.

First operator-started following session produced real bounded wrist turns,
with no reported controller faults and fixed base/shoulder joints. Its detailed
result and operator feedback are recorded in the session log after it ends.
No grasp, hand depth or autonomous gesture pickup is implied by this demo.

75 offline tests currently pass, including heartbeat expiry, lost/fist/multiple
hand, duplicate frames, bounded turns, stop during planning, HTTP intent checks,
pickup/follow exclusion, display rotation and wrist-only motion limits.

Operator feedback after 37 wrist turns: partly worked, but choppy/minimal;
wanted fluid base/arm participation. The broader puppy-demo goal remains active.
The current prototype does not yet meet that behavior; continuous control and
a checked base-motion range are next.
