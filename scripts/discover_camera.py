#!/usr/bin/env python3
"""List devices via DepthAI discovery; do not open a device or start a pipeline."""

import depthai as dai


def main():
    print("DepthAI version:", dai.__version__)
    devices = dai.Device.getAllAvailableDevices()
    print("Devices discovered:", len(devices))
    for device in devices:
        print("Address/name:", device.name)
        print("Protocol:", device.protocol)
        print("State:", device.state)
    if not devices:
        print("No devices discovered. This does not prove the camera is absent.")


if __name__ == "__main__":
    main()
