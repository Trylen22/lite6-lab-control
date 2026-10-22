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

The user requires this repo to be heavily commented, educational, and clean. Explain units, coordinate frames, preprocessing assumptions, SDK return codes, concurrency boundaries, and failure handling near the relevant code. Keep modules focused, format browser assets for reading, and maintain exercises, architecture, and an incremental roadmap in docs/. Never describe pixel detections as calibrated pickup targets. The user subsequently authorized one supervised pickup, a two-second hold, and release with the operator at the emergency stop. This authorization does not supply verified target/contact coordinates, TCP/tool configuration, or calibration. Two initial cycles stopped at attachment timeout before motion. After the operator adjusted contact, a stationary test confirmed feedback 1, and one explicitly authorized 2 mm upward lift/two-second hold/release-at-hover trial completed. There was no commanded descent into the compressed contact. Final pose and tool-off state were verified; actual object clearance is not independently measured. Preserve the feedback gate and the distinction between measured robot travel, cup compliance, operator observations, and camera calibration. Further repetitions or larger motions require a fresh concrete user request and validated current geometry. Establish those prerequisites before implementing/executing this specific cycle; do not broaden it into repeated automation.
