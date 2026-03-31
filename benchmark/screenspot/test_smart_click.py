#!/usr/bin/env python3
"""Quick validation of smart_click against ScreenSpot benchmark entries."""
import json
import subprocess
import random
from pathlib import Path

SCREENSPOT_DIR = Path.home() / "devel/ScreenSpot"
DATASET = SCREENSPOT_DIR / "screenspot_desktop.json"
IMAGES = SCREENSPOT_DIR / "screenspot_imgs"
SMART_CLICK = Path.home() / "bin/smart_click"


def point_in_bbox(px, py, bbox):
    bx, by, bw, bh = bbox
    return bx <= px <= bx + bw and by <= py <= by + bh


with open(DATASET) as f:
    data = json.load(f)

rng = random.Random(42)
sample = rng.sample(data, 20)

hits = 0
total = 0

for i, entry in enumerate(sample):
    img = IMAGES / entry["img_filename"]
    instruction = entry["instruction"].strip()
    gt = entry["bbox"]
    dtype = entry["data_type"]

    result = subprocess.run(
        [str(SMART_CLICK), instruction, "--file", str(img),
         "--dry-run", "--json"],
        capture_output=True, text=True, timeout=30,
    )

    total += 1
    if result.returncode == 0:
        out = json.loads(result.stdout)
        px, py = out["x"], out["y"]
        hit = point_in_bbox(px, py, gt)
        if hit:
            hits += 1
        status = "HIT" if hit else "MISS"
        method = out.get("method", "?")
        print(f"  [{i+1:>2}] {status:<4s} {dtype:4s} {method:<12s} "
              f"'{instruction[:40]}'  pred=({px},{py})")
    else:
        print(f"  [{i+1:>2}] FAIL {dtype:4s} "
              f"'{instruction[:40]}'  (exit {result.returncode})")

print(f"\nAccuracy: {hits}/{total} = {hits/total:.1%}")
