# Project instructions

## Scope

This repository owns Lite 6 and OAK-D Pro PoE work. Do not modify, deploy to, or commit changes in the sibling JETMAX project as part of this work. Do not copy its credentials, device addresses, motion limits, saved poses, or camera offsets here.

## Device work

Start with local inspection and read-only device status. Do not enable motion, release brakes, change I/O, operate a tool, reset network settings, flash firmware, or configure automatic startup without a concrete user request covering that operation. Confirm which physical device is being addressed. Before motion, establish the mounting, reachable emergency stop, tool/payload configuration, workspace, and low-speed trial with the operator present.

Do not reuse JetMax coordinates, calibration, or motion code as Lite 6 defaults. Do not make an example command move hardware on import or startup. Keep observation, manual motion, and automation separate. Document actual stop behavior; a dashboard stop is not automatically an emergency stop.

## Configuration and version control

Keep actual machine configuration and credentials under ignored `local/` or outside the repository. Commit sanitized examples. Do not embed secrets in scripts or remote URLs. Review staged content before pushing. Keep this repo private unless the user requests otherwise.

Pin dependencies after confirming host and device compatibility. Record changes, checks, and remaining physical validation in docs/STATUS.md. Push completed work to this project's GitHub remote as requested by the user; never claim a push succeeded without checking it.

## Classroom purpose

The user requires this repo to be heavily commented, educational, and clean. Explain units, coordinate frames, preprocessing assumptions, SDK return codes, concurrency boundaries, and failure handling near the relevant code. Keep modules focused, format browser assets for reading, and maintain exercises, architecture, and an incremental roadmap in docs/. Never describe pixel detections as calibrated pickup targets. Current user instruction: no robot motion; build UI and explore SDK/vision only.
