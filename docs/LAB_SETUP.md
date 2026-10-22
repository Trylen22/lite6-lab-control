# Lab setup and first access

## Identify the existing installation

Record these in ignored `local/inventory.md`:

- Robot label, asset identifier, current power supply, and emergency-stop connection.
- Base mounting, workspace clearance, attached tool, tool cables/tubing, and payload information.
- Robot IP label and existing network wiring. Ask whether other software currently controls the arm.
- Exact camera label, mount location (arm or fixed), Ethernet connection, and PoE switch/injector.
- Existing lab computer, OS, Python version, available disk/RAM, and account/access arrangements.
- Whether the spare original Jetson Nano will be used; it has not been inspected for this project.

Photographs can help identify connectors; do not commit images containing credentials or private lab information.

## First connection

1. Inspect the existing setup with the lab operator. Preserve working cabling and configuration.
2. Identify the host and run `./scripts/host_inventory.sh` there. Redirect to `local/host-inventory.txt` if desired. Review output before sharing.
3. Confirm robot and camera addresses and the host network interface/subnet. Record actual values locally. Do not assume JetMax addresses apply, scan unrelated lab networks, or reset device networking to guess an address.
4. Access the robot status interface without enabling motion. Record firmware, errors, and configuration; do not clear errors blindly or update firmware.
5. Select compatible UFACTORY SDK and Luxonis DepthAI versions for the host. Record versions and installation commands when verified.
6. Establish camera viewing without motion. The OAK camera requires its own suitable power arrangement, normally PoE; a standard Ethernet port alone does not supply PoE.
7. Add low-speed manual movement only after the operator confirms mounting, emergency stop, payload/tool configuration, and clear motion space.
8. Teach this arm's positions. Calibrate camera-to-robot geometry before automated reaching or picking.

## Remote access

SSH connects to the host computer running our software. Do not assume either device exposes a supported SSH login. A lab desktop or the spare Nano may serve as the host; remote access requires that host to stay powered, networked, and configured under lab policy. Network access is not proof that unattended motion is appropriate.

## Manufacturer references

- [UFACTORY Studio connection](https://docs.usermanual.ufactory.cc/user_manual/ufactoryStudio/3.connection.html)
- [UFACTORY Python SDK](https://github.com/xArm-Developer/xArm-Python-SDK)
- [OAK-D Pro PoE hardware](https://docs.luxonis.com/hardware/products/OAK-D%20Pro%20PoE)
- [Luxonis PoE deployment](https://docs.luxonis.com/hardware/platform/deploy/poe-deployment-guide)
- [UFACTORY vision example](https://docs.supportarticle.ufactory.cc/support_articles/developer/ufactory-vision.html)

These links are starting references; installation/API compatibility must be checked against the actual host before implementation.
