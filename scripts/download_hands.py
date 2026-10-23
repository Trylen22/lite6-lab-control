#!/usr/bin/env python3
"""Download the official MediaPipe gesture/landmark bundle; never runs during UI startup."""

import hashlib
from pathlib import Path
import urllib.request

# Model stays in ignored local/ rather than bloating Git with binary weights.
ROOT = Path(__file__).resolve().parents[1]
URL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
EXPECTED_SHA256 = "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"


def main():
    target = ROOT / "local/models/gesture_recognizer.task"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temp = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(URL, timeout=60) as source:
                temp.write_bytes(source.read())
            digest = hashlib.sha256(temp.read_bytes()).hexdigest()
            if digest != EXPECTED_SHA256:
                raise RuntimeError(
                    "Model checksum mismatch; downloaded file was not installed"
                )
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Existing model does not match the pinned release checksum")
    print(target)
    print("SHA256:", hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
