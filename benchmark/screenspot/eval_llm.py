#!/usr/bin/env python3
"""ScreenSpot benchmark: LLM reasoning approach.

Sends each screenshot + instruction to Claude and asks it to predict
the click coordinates. Compares against ground truth bounding box.

Usage:
  python eval_llm.py                         20 random entries, Haiku
  python eval_llm.py --model sonnet          Use Sonnet
  python eval_llm.py --n 50                  50 random entries
  python eval_llm.py --seed 42               Reproducible random subset
  python eval_llm.py --type text             Text entries only
  python eval_llm.py --compare               Compare with OCR results
"""
import sys
import os
import json
import time
import random
import base64
import re
import argparse
from pathlib import Path
from dataclasses import dataclass

import anthropic

# --- Configuration ---

SCREENSPOT_DIR = Path(os.environ.get(
    "SCREENSPOT_DIR",
    os.path.expanduser("~/devel/ScreenSpot")
))
DATASET_FILE = SCREENSPOT_DIR / "screenspot_desktop.json"
IMAGES_DIR = SCREENSPOT_DIR / "screenspot_imgs"
RESULTS_DIR = Path(__file__).parent / "results"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

SYSTEM_PROMPT = """You are a UI element locator. Given a screenshot and an instruction describing a UI element to interact with, you must identify the exact pixel coordinates to click.

Rules:
- Output ONLY the coordinates in the format: CLICK(x, y)
- x is the horizontal pixel position from the left edge
- y is the vertical pixel position from the top edge
- Click the CENTER of the target UI element
- Consider the full image dimensions when estimating coordinates
- Do not explain your reasoning, just output CLICK(x, y)"""

USER_PROMPT_TEMPLATE = """Image dimensions: {width}x{height} pixels

Instruction: {instruction}

Where should I click? Respond with CLICK(x, y) only."""

COORD_PATTERN = re.compile(r"CLICK\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)")


# --- Helpers ---

def point_in_bbox(px, py, bbox):
    bx, by, bw, bh = bbox
    return bx <= px <= bx + bw and by <= py <= by + bh


def bbox_center(bbox):
    return bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2


def euclidean_dist(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def load_image_b64(path):
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_image_dims(path):
    """Get image width x height without heavy dependencies."""
    # Read PNG header: width at bytes 16-20, height at bytes 20-24
    with open(path, "rb") as f:
        header = f.read(32)
    if header[:4] == b"\x89PNG":
        import struct
        w, h = struct.unpack(">II", header[16:24])
        return w, h
    # Fallback to cv2
    import cv2
    img = cv2.imread(str(path))
    return img.shape[1], img.shape[0]


def parse_click(response_text):
    """Extract (x, y) from LLM response."""
    m = COORD_PATTERN.search(response_text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: look for any two numbers that could be coordinates
    nums = re.findall(r"\b(\d{2,4})\b", response_text)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return None


# --- Main ---

def run_evaluation(args):
    client = anthropic.Anthropic()
    model_id = MODEL_MAP.get(args.model, args.model)

    # Load dataset
    with open(DATASET_FILE) as f:
        dataset = json.load(f)

    if args.type:
        dataset = [e for e in dataset if e["data_type"] == args.type]

    # Random subset
    rng = random.Random(args.seed)
    if args.n < len(dataset):
        dataset = rng.sample(dataset, args.n)

    print(f"ScreenSpot Desktop — LLM Reasoning Benchmark")
    print(f"{'=' * 65}")
    print(f"Model:   {model_id}")
    print(f"Entries: {args.n} (seed={args.seed})")
    types = {}
    for e in dataset:
        types[e["data_type"]] = types.get(e["data_type"], 0) + 1
    print(f"Types:   {types}")
    print()

    results = []
    hits = 0
    misses = 0
    parse_fails = 0
    total_dist = 0.0
    distances = []

    hits_by_type = {"text": 0, "icon": 0}
    total_by_type = {"text": 0, "icon": 0}

    t0 = time.time()

    for i, entry in enumerate(dataset):
        img_path = IMAGES_DIR / entry["img_filename"]
        instruction = entry["instruction"].strip()
        gt_bbox = entry["bbox"]
        gt_cx, gt_cy = bbox_center(gt_bbox)
        data_type = entry["data_type"]

        if not img_path.exists():
            print(f"  [{i+1}] SKIP - image not found")
            continue

        total_by_type[data_type] += 1
        width, height = get_image_dims(str(img_path))
        img_b64 = load_image_b64(str(img_path))

        # Call Claude
        t_start = time.time()
        try:
            response = client.messages.create(
                model=model_id,
                max_tokens=100,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": USER_PROMPT_TEMPLATE.format(
                                width=width, height=height,
                                instruction=instruction,
                            ),
                        },
                    ],
                }],
            )
            reply = response.content[0].text
            latency = time.time() - t_start
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
        except Exception as e:
            print(f"  [{i+1}] API ERROR: {e}")
            results.append({
                "index": i, "instruction": instruction,
                "data_type": data_type, "error": str(e),
            })
            continue

        # Parse coordinates
        coords = parse_click(reply)
        hit = False
        dist = None

        if coords:
            px, py = coords
            hit = point_in_bbox(px, py, gt_bbox)
            dist = euclidean_dist((px, py), (gt_cx, gt_cy))
            distances.append(dist)
            total_dist += dist
            if hit:
                hits += 1
                hits_by_type[data_type] += 1
            else:
                misses += 1
        else:
            parse_fails += 1

        status = "HIT" if hit else ("PARSE_FAIL" if coords is None else "MISS")
        pred_str = f"({px},{py})" if coords else "???"
        dist_str = f"d={dist:.0f}" if dist is not None else ""

        print(f"  [{i+1:>2}/{len(dataset)}] {status:<10} {data_type:4s} "
              f"'{instruction[:40]:<40s}' pred={pred_str:<12s} "
              f"gt=({gt_cx},{gt_cy}) {dist_str}  [{latency:.1f}s]")

        results.append({
            "index": i,
            "instruction": instruction,
            "data_type": data_type,
            "data_source": entry["data_source"],
            "img_filename": entry["img_filename"],
            "gt_bbox": gt_bbox,
            "gt_center": [gt_cx, gt_cy],
            "pred": list(coords) if coords else None,
            "hit": hit,
            "distance": round(dist, 1) if dist is not None else None,
            "reply": reply,
            "latency": round(latency, 2),
        })

    elapsed = time.time() - t0
    total = len(dataset)

    print(f"\n{'=' * 65}")
    print(f"RESULTS — {model_id}")
    print(f"{'=' * 65}")
    print(f"Total:       {total}")
    print(f"Hits:        {hits}  ({hits/total:.1%})")
    print(f"Misses:      {misses}  ({misses/total:.1%})")
    print(f"Parse fails: {parse_fails}")
    print()

    for dtype in ["text", "icon"]:
        t = total_by_type[dtype]
        h = hits_by_type[dtype]
        if t > 0:
            print(f"  {dtype:>4s}: {h}/{t} = {h/t:.1%}")
    print()

    if distances:
        distances.sort()
        mean_d = sum(distances) / len(distances)
        median_d = distances[len(distances) // 2]
        print(f"Distance (pred→gt_center):")
        print(f"  Mean:   {mean_d:.1f} px")
        print(f"  Median: {median_d:.1f} px")
        print(f"  Min:    {distances[0]:.1f} px")
        print(f"  Max:    {distances[-1]:.1f} px")
    print(f"\nTime: {elapsed:.1f}s total, {elapsed/total:.1f}s/entry")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"llm_{args.model}_n{args.n}_s{args.seed}.json"
    output = {
        "benchmark": "ScreenSpot Desktop — LLM Reasoning",
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "model": model_id,
        "n": args.n,
        "seed": args.seed,
        "elapsed_seconds": round(elapsed, 1),
        "accuracy": round(hits / total, 4) if total else 0,
        "accuracy_text": round(hits_by_type["text"] / total_by_type["text"], 4) if total_by_type["text"] else 0,
        "accuracy_icon": round(hits_by_type["icon"] / total_by_type["icon"], 4) if total_by_type["icon"] else 0,
        "mean_distance": round(sum(distances) / len(distances), 1) if distances else None,
        "median_distance": round(distances[len(distances) // 2], 1) if distances else None,
        "entries": results,
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {out_file}")


def parse_args():
    parser = argparse.ArgumentParser(description="ScreenSpot LLM reasoning benchmark")
    parser.add_argument("--model", default="haiku", choices=list(MODEL_MAP.keys()),
                        help="Claude model to use (default: haiku)")
    parser.add_argument("--n", type=int, default=20, help="Number of random entries")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--type", choices=["text", "icon"], help="Filter by type")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_evaluation(args)
