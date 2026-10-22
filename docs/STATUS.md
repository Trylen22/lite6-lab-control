# Project status

## 2026-10-22 — Separate project initialization

- Workspace: `/home/wavyjones/Desktop/LITE6`.
- Intended GitHub repository: `Trylen22/lite6-lab-control` (private).
- Known hardware from discussion: UFACTORY Lite 6, label model LI10; Luxonis OAK-D Pro PoE.
- Host decision pending: existing lab PC versus spare original Jetson Nano dev kit.
- JetMax remains a separate project with its existing local changes untouched.
- Added setup documentation, ignored local configuration, project instructions, and local host-inventory script.
- No device connection or physical control has been attempted for this project.
- No hardware SDK dependencies installed or pinned yet; compatibility is unverified.

## Next session

Identify existing lab wiring, tool, emergency stop, addresses, and host. Record system inventory. Start with status and camera viewing; motion and automation follow separate verification.

## Validation

Passed: shell syntax check, local host-inventory execution on the development workstation, example TOML parsing, ignored local configuration/capture/secret path checks, and staged whitespace/content review. The local inventory output is ignored. Physical functionality remains untested. GitHub synchronization is verified separately after publishing.

## First lab network attempt

- Operator supplied a robot web endpoint; stored only in ignored local configuration.
- Created a dedicated laptop Ethernet profile with a static address, no default gateway, duplicate-address detection, and autoconnect disabled. Wi-Fi configuration unchanged.
- Target ping and HTTP requests timed out. Final inspection showed Ethernet carrier off, so connectivity and device identity remain unverified.
- Next: restore physical Ethernet link and retry only the supplied endpoint. No robot settings or motion commands were sent.

## Lab web connectivity confirmed

- Operator corrected the target address, recorded in ignored local configuration.
- Ethernet ping: two replies, zero packet loss.
- HTTP on port 18333: 200 OK; page title UFactory Studio.
- Network and web connectivity are now established. Robot identity, status, and camera access remain to be inspected. No motion or robot configuration commands sent.

## Camera discovery attempt

- Ethernet-only discovery found one additional responding address besides the arm and laptop. This remains an unverified camera candidate and may be switch infrastructure. Actual address and MAC are stored locally.
- No open TCP 11490 result in a limited subnet probe; DepthAI discovery returned zero devices. Neither check establishes camera absence.
- Added a discovery-only utility and pinned the dependency versions installed in this project's ignored virtual environment on the Linux x86_64/Python 3.12 laptop. Original Nano compatibility is not established.
- Utility executed successfully and reported zero devices. No camera stream, firmware update, configuration write, or robot motion was initiated.
- Next: confirm camera power/link and compare the label MAC with the candidate address, then repeat discovery.

## Additional candidate identification

- Additional responding device offers SSH (Dropbear 2020.81), with tested web/RTSP/DepthAI ports closed.
- MAC vendor lookup indicates Ubiquiti; the device is likely network infrastructure, but exact model has not been confirmed. Vendor discovery query received no reply.
- No authentication, device configuration change, or stream initialization was attempted. Camera identification remains pending.
