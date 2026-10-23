#!/usr/bin/env python3
"""Render the explainer film (assets/explainer) to stills or an MP4.

Same approach as Hunt_Project/animationns/html/render_video.py: the page draws
every frame as a pure function of time, so we call window.render(t) at fixed
steps in headless Chrome and screenshot each frame. The page loads meshes and
calibration over HTTP, so the lab deck must be running (./run.sh).

Needs Python with Playwright (e.g. ~/Desktop/Hunt_Project/.venv/bin/python)
and ffmpeg for video:

  python scripts/render_explainer.py --stills 5 30 "Align@4" --out /tmp/shots
  python scripts/render_explainer.py --video --out docs/explainer.mp4 [--fps 30]
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

URL = "http://127.0.0.1:8100/explainer?auto=1"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stills", nargs="*", help='times in seconds, or "Scene@seconds"')
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--url", default=URL)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = Path(a.out)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=[
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--hide-scrollbars",
            ],
        )
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080}, device_scale_factor=1
        )
        page.goto(a.url, wait_until="load")
        page.wait_for_function("typeof window.render === 'function'", timeout=60000)
        total = page.evaluate("window.TOTAL")
        scenes = {s["name"]: s for s in page.evaluate("window.SCENES")}
        print(f"explainer: {total:.1f} s, {len(scenes)} scenes", flush=True)
        if a.stills is not None:
            out.mkdir(parents=True, exist_ok=True)
            for spec in a.stills:
                if "@" in spec:
                    name, local = spec.split("@")
                    t = scenes[name]["start"] + float(local)
                else:
                    t = float(spec)
                page.evaluate(f"window.render({t})")
                path = out / f"t{t:07.2f}.png"
                page.screenshot(path=str(path))
                print("wrote", path, flush=True)
        if a.video:
            frames = Path(tempfile.mkdtemp(prefix="explainer_"))
            n = int(total * a.fps)
            t0 = time.time()
            for i in range(n):
                page.evaluate(f"window.render({i / a.fps})")
                page.screenshot(path=str(frames / f"{i:05d}.png"))
                if i % (a.fps * 10) == 0:
                    print(f"  frame {i}/{n}  {time.time() - t0:5.0f}s", flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(a.fps),
                    "-i",
                    str(frames / "%05d.png"),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "18",
                    "-preset",
                    "medium",
                    "-movflags",
                    "+faststart",
                    str(out),
                ],
                check=True,
            )
            shutil.rmtree(frames, ignore_errors=True)
            print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
        browser.close()


if __name__ == "__main__":
    main()
