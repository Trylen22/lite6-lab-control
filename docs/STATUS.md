# Current project status

Updated 2026-10-22. Historical connection attempts are preserved in [session history](SESSION_LOG.md).

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

No robot motion, enable, reset, fault clearing, mode changes, or tool commands were sent. No movement endpoint exists. No camera firmware/network write, continuous recording, cloud inference, or IR emitter control was added. There is no camera-to-robot calibration or lab-part training yet.

## Next

Open the deck in the lab browser, review the layout and mode controls, and follow [the classroom guide](CLASSROOM_GUIDE.md). Document mounting/tool geometry and lighting. See [the roadmap](ROADMAP.md) for calibration and later supervised motion checkpoints. The user explicitly excluded motion from this phase.

## Suction calibration research

Found official camera dimensions, Lite vacuum URDF, UFACTORY OAK mount STEP, and the vendor's OAK/Lite 6 grasping example. The example uses a tuned 55 mm flange-to-grip parameter; the URDF defines a 61 mm local TCP. Neither establishes the actual installed cup geometry. Research and a measured-calibration procedure are documented in CALIBRATION_PLAN.md. No vendor motion demo was executed, no nominal offsets applied, and no robot/camera configuration was changed. Physical mounting confirmation remains pending.

## Supervised single pickup requested — geometry pending

The operator authorized one pickup, two-second hold, and release, and stated they can operate the emergency stop. Read-only inspection confirms a fresh green detection and unchanged robot pose; it does not establish the physical cup location or contact height. No move, enable, suction, or reset was issued. Next prerequisite is verified tool/TCP configuration and measured/taught approach/contact geometry, followed by a bounded supervised cycle. This is missing physical information, not a request for repeated authorization.
