#!/usr/bin/env python3
"""Download the small official YOLOX-Nano model; never runs during UI startup."""

import hashlib
from pathlib import Path
import urllib.request

# Model stays in ignored local/ rather than bloating Git with binary weights.
ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
EXPECTED_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"


def main():
    target = ROOT / "local/models/yolox_nano.onnx"
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
