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

Current authorized speed scale is **1.3225**: two compounded 15% increases.
Travel/return 6.6125 mm/s, lift/lower 2.645 mm/s, final search 0.66125 mm/s.
Accelerations and the two-second hold are unchanged.

## Software checks

55 offline tests pass. Coverage includes frame freshness/session identity,
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
