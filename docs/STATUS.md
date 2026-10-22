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
