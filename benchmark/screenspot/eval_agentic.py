#!/usr/bin/env python3
"""ScreenSpot benchmark: Agentic LLM with tool use.

Gives the LLM access to detection tools + its own visual estimation:
  - ocr_scan: run OCR, get all text regions with bounding boxes
  - yolo_detect: run YOLO-World with custom class names
  - visual_estimate: use the LLM's own vision to estimate coordinates directly
  - click: submit final answer

Usage:
  python eval_agentic.py                       20 random entries, Haiku
  python eval_agentic.py --model sonnet        Use Sonnet
  python eval_agentic.py --n 50                50 random entries
  python eval_agentic.py --seed 42             Reproducible subset
  python eval_agentic.py --max-turns 5         Max tool-use rounds
"""
import sys
import os
import json
import time
import base64
import random
import struct
import argparse
import urllib.request
import urllib.parse
from pathlib import Path

import anthropic

# --- Config ---

SCREENSPOT_DIR = Path(os.environ.get(
    "SCREENSPOT_DIR", os.path.expanduser("~/devel/ScreenSpot")
))
DATASET_FILE = SCREENSPOT_DIR / "screenspot_desktop.json"
IMAGES_DIR = SCREENSPOT_DIR / "screenspot_imgs"
RESULTS_DIR = Path(__file__).parent / "results"

OCR_URL = "http://127.0.0.1:18200"
YOLO_URL = "http://127.0.0.1:18201"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

SYSTEM_PROMPT = """You are a UI element locator with tools to analyze a screenshot.

Task: given an instruction describing a UI element, find its exact pixel coordinates and click it.

Your tools:

1. **ocr_scan** — finds all text on screen with bounding boxes. Use for text labels, menus, buttons with text.

2. **yolo_detect** — finds objects by class name. Use for visual elements like icons, buttons, images.

3. **visual_estimate** — use your own vision to estimate coordinates. You CAN see the screenshot. When OCR and YOLO don't find the target, look at the image yourself and estimate where the element is. This is especially useful for icons, small UI controls, and elements that text/object detection misses.

4. **click** — submit your final answer (pixel coordinates).

Strategy:
- For text targets: ocr_scan first, use the matched text's center coordinates
- For icon targets: try yolo_detect once. If YOLO doesn't find it, immediately use visual_estimate — do NOT retry YOLO with many different class names
- visual_estimate is your fallback for anything OCR/YOLO can't find — use it confidently
- You MUST call click to submit your answer — do not just describe coordinates in text
- Be efficient: 2-3 tool calls should suffice for most entries"""

TOOLS = [
    {
        "name": "ocr_scan",
        "description": "Run OCR on the screenshot. Returns all detected text regions with bounding boxes and center coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional: filter to text matching this query (case-insensitive). Omit to get all text.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "yolo_detect",
        "description": "YOLO-World object detection with custom class names. Returns detected objects with bounding boxes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "classes": {
                    "type": "string",
                    "description": "Comma-separated class names (e.g., 'close button,minimize icon,gear,arrow')",
                },
                "confidence": {
                    "type": "number",
                    "description": "Min confidence 0-1 (default: 0.05)",
                    "default": 0.05,
                },
            },
            "required": ["classes"],
        },
    },
    {
        "name": "visual_estimate",
        "description": "Use your own visual understanding of the screenshot to estimate where a UI element is. Look at the image and estimate pixel coordinates. Use this when OCR and YOLO fail — especially for icons, small buttons, and visual elements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element_description": {
                    "type": "string",
                    "description": "What you're looking for in the screenshot",
                },
                "estimated_x": {
                    "type": "integer",
                    "description": "Estimated horizontal pixel coordinate",
                },
                "estimated_y": {
                    "type": "integer",
                    "description": "Estimated vertical pixel coordinate",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "How confident you are",
                },
            },
            "required": ["element_description", "estimated_x", "estimated_y"],
        },
    },
    {
        "name": "click",
        "description": "Submit final answer: the pixel coordinates to click.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Horizontal pixel from left edge"},
                "y": {"type": "integer", "description": "Vertical pixel from top edge"},
                "reasoning": {"type": "string", "description": "Brief explanation"},
            },
            "required": ["x", "y"],
        },
    },
]


# --- Helpers ---

def point_in_bbox(px, py, bbox):
    bx, by, bw, bh = bbox
    return bx <= px <= bx + bw and by <= py <= by + bh

def bbox_center(bbox):
    return bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2

def get_image_dims(path):
    with open(path, "rb") as f:
        header = f.read(32)
    if header[:4] == b"\x89PNG":
        w, h = struct.unpack(">II", header[16:24])
        return w, h
    import cv2
    img = cv2.imread(str(path))
    return img.shape[1], img.shape[0]


# --- Tool implementations ---

def run_ocr(image_path, query=None):
    with open(image_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{OCR_URL}/ocr", data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    regions = json.loads(resp.read().decode())
    if query:
        q = query.lower()
        regions = [r for r in regions if q in r["text"].lower()]
    if len(regions) > 40:
        regions = regions[:40]
    return regions


def run_yolo(image_path, classes, confidence=0.05):
    with open(image_path, "rb") as f:
        data = f.read()
    params = urllib.parse.urlencode({"classes": classes, "conf": confidence, "mode": "world"})
    req = urllib.request.Request(
        f"{YOLO_URL}/detect?{params}", data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    detections = json.loads(resp.read().decode())
    if len(detections) > 20:
        detections = detections[:20]
    return detections


def execute_tool(tool_name, tool_input, image_path):
    """Execute a tool call. Returns result string."""

    if tool_name == "ocr_scan":
        regions = run_ocr(image_path, tool_input.get("query"))
        if not regions:
            return "No text detected" + (f" matching '{tool_input.get('query')}'" if tool_input.get("query") else "") + "."
        lines = []
        for r in regions:
            lines.append(f"  text=\"{r['text']}\"  center=({r['center'][0]},{r['center'][1]})  "
                         f"bbox=[{r['bbox'][0]},{r['bbox'][1]},{r['bbox'][2]},{r['bbox'][3]}]  "
                         f"conf={r['confidence']}")
        return f"Found {len(regions)} text regions:\n" + "\n".join(lines)

    elif tool_name == "yolo_detect":
        classes = tool_input.get("classes", "object")
        conf = tool_input.get("confidence", 0.05)
        try:
            detections = run_yolo(image_path, classes, conf)
        except Exception as e:
            return f"YOLO error: {e}"
        if not detections:
            return f"No objects detected for: {classes}. Try visual_estimate instead."
        lines = []
        for d in detections:
            lines.append(f"  class=\"{d['class']}\"  center=({d['center'][0]},{d['center'][1]})  "
                         f"bbox=[{d['bbox'][0]},{d['bbox'][1]},{d['bbox'][2]},{d['bbox'][3]}]  "
                         f"conf={d['confidence']}")
        return f"Found {len(detections)} objects:\n" + "\n".join(lines)

    elif tool_name == "visual_estimate":
        x = tool_input.get("estimated_x", 0)
        y = tool_input.get("estimated_y", 0)
        desc = tool_input.get("element_description", "")
        conf = tool_input.get("confidence", "medium")
        return (f"Visual estimate recorded: ({x}, {y}) for \"{desc}\" "
                f"(confidence: {conf}). Use click tool to submit these coordinates.")

    elif tool_name == "click":
        return "CLICK_SUBMITTED"

    return f"Unknown tool: {tool_name}"


# --- Agent loop ---

def run_agent(client, model_id, image_path, instruction, max_turns=5):
    """Run the agentic tool-use loop. Returns (click_xy, tool_log, in_tokens, out_tokens)."""
    w, h = get_image_dims(str(image_path))

    with open(image_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
            {"type": "text", "text": f"Image dimensions: {w}x{h} pixels\n\nInstruction: {instruction}\n\nFind and click the target UI element."},
        ],
    }]

    total_in = 0
    total_out = 0
    tool_log = []

    for turn in range(max_turns):
        response = client.messages.create(
            model=model_id,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_log.append({"tool": tool_name, "input": tool_input, "turn": turn})

                if tool_name == "click":
                    tool_log[-1]["reasoning"] = tool_input.get("reasoning", "")
                    return (tool_input.get("x"), tool_input.get("y")), tool_log, total_in, total_out

                result_text = execute_tool(tool_name, tool_input, str(image_path))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        if not tool_results:
            import re
            for block in response.content:
                if block.type == "text":
                    m = re.search(r"CLICK\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", block.text)
                    if m:
                        return (int(m.group(1)), int(m.group(2))), tool_log, total_in, total_out
            break

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if response.stop_reason == "end_turn":
            break

    return None, tool_log, total_in, total_out


# --- Evaluation ---

def run_evaluation(args):
    client = anthropic.Anthropic()
    model_id = MODEL_MAP.get(args.model, args.model)

    with open(DATASET_FILE) as f:
        dataset = json.load(f)
    if args.type:
        dataset = [e for e in dataset if e["data_type"] == args.type]

    rng = random.Random(args.seed)
    if args.n < len(dataset):
        dataset = rng.sample(dataset, args.n)

    total = len(dataset)
    type_counts = {}
    for e in dataset:
        type_counts[e["data_type"]] = type_counts.get(e["data_type"], 0) + 1

    print(f"ScreenSpot Desktop — Agentic LLM (OCR + YOLO + visual_estimate)")
    print(f"{'=' * 70}")
    print(f"Model:      {model_id}")
    print(f"Entries:    {total} (seed={args.seed})")
    print(f"Types:      {type_counts}")
    print(f"Max turns:  {args.max_turns}")
    print()

    results = []
    hits = 0
    hits_by_type = {"text": 0, "icon": 0}
    total_by_type = {"text": 0, "icon": 0}
    total_in_tokens = 0
    total_out_tokens = 0
    total_tool_calls = 0
    tool_usage = {}

    t0 = time.time()

    for i, entry in enumerate(dataset):
        img_path = IMAGES_DIR / entry["img_filename"]
        instruction = entry["instruction"].strip()
        gt_bbox = entry["bbox"]
        gt_cx, gt_cy = bbox_center(gt_bbox)
        dtype = entry["data_type"]
        total_by_type[dtype] += 1

        if not img_path.exists():
            print(f"  [{i+1}] SKIP")
            continue

        t_start = time.time()
        try:
            click_result, tool_log, in_tok, out_tok = run_agent(
                client, model_id, img_path, instruction, args.max_turns
            )
        except Exception as e:
            print(f"  [{i+1:>2}] ERROR  {dtype:4s} '{instruction[:35]}'  {e}")
            results.append({"index": i, "instruction": instruction, "data_type": dtype, "error": str(e), "hit": False})
            continue

        latency = time.time() - t_start
        total_in_tokens += in_tok
        total_out_tokens += out_tok

        n_tools = len(tool_log)
        total_tool_calls += n_tools
        for tc in tool_log:
            tool_usage[tc["tool"]] = tool_usage.get(tc["tool"], 0) + 1

        hit = False
        px, py = 0, 0
        if click_result:
            try:
                sx, sy = str(click_result[0]).strip(), str(click_result[1]).strip()
                if "," in sx:
                    parts = sx.split(",")
                    sx, sy = parts[0].strip(), parts[1].strip()
                px, py = int(float(sx)), int(float(sy))
                hit = point_in_bbox(px, py, gt_bbox)
                if hit:
                    hits += 1
                    hits_by_type[dtype] += 1
            except (ValueError, TypeError):
                pass

        status = "HIT " if hit else ("FAIL" if click_result is None else "MISS")
        tools_used = [tc["tool"] for tc in tool_log if tc["tool"] != "click"]
        tool_str = ",".join(tools_used) if tools_used else "none"
        reasoning = next((tc.get("reasoning", "")[:50] for tc in tool_log if tc.get("reasoning")), "")
        reason_str = f" | {reasoning}" if reasoning else ""

        print(f"  [{i+1:>2}/{total}] {status} {dtype:4s} "
              f"'{instruction[:32]:<32s}' pred=({px},{py}) "
              f"[{tool_str}] [{latency:.1f}s]{reason_str}")

        results.append({
            "index": i, "instruction": instruction, "data_type": dtype,
            "data_source": entry["data_source"], "img_filename": entry["img_filename"],
            "gt_bbox": gt_bbox, "gt_center": [gt_cx, gt_cy],
            "pred": [px, py] if click_result else None, "hit": hit,
            "tool_log": tool_log, "n_tools": n_tools,
            "latency": round(latency, 2), "input_tokens": in_tok, "output_tokens": out_tok,
        })

    elapsed = time.time() - t0

    print(f"\n{'=' * 70}")
    print(f"RESULTS — {model_id} (agentic + visual_estimate)")
    print(f"{'=' * 70}")
    print(f"Total:       {total}")
    print(f"Hits:        {hits}  ({hits/total:.1%})")
    print()
    for dtype in ["text", "icon"]:
        t = total_by_type[dtype]
        h = hits_by_type[dtype]
        if t > 0:
            print(f"  {dtype:>4s}: {h}/{t} = {h/t:.1%}")
    print()
    print(f"Tool usage:")
    for tool, count in sorted(tool_usage.items()):
        print(f"  {tool}: {count}")
    print(f"  avg tools/entry: {total_tool_calls/total:.1f}")
    print()

    if "haiku" in model_id:
        cost = total_in_tokens * 0.80 / 1e6 + total_out_tokens * 4.0 / 1e6
    elif "sonnet" in model_id:
        cost = total_in_tokens * 3.0 / 1e6 + total_out_tokens * 15.0 / 1e6
    else:
        cost = total_in_tokens * 15.0 / 1e6 + total_out_tokens * 75.0 / 1e6
    print(f"Tokens: {total_in_tokens:,} in / {total_out_tokens:,} out  Cost: ${cost:.2f}")
    print(f"Time: {elapsed:.1f}s ({elapsed/total:.1f}s/entry)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"agentic_{args.model}_n{args.n}_s{args.seed}.json"
    output = {
        "benchmark": "ScreenSpot Desktop — Agentic LLM + visual_estimate",
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "model": model_id, "n": args.n, "seed": args.seed,
        "max_turns": args.max_turns,
        "accuracy": round(hits / total, 4),
        "accuracy_text": round(hits_by_type["text"] / max(total_by_type["text"], 1), 4),
        "accuracy_icon": round(hits_by_type["icon"] / max(total_by_type["icon"], 1), 4),
        "total_input_tokens": total_in_tokens,
        "total_output_tokens": total_out_tokens,
        "tool_usage": tool_usage,
        "entries": results,
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_file}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="haiku", choices=list(MODEL_MAP.keys()))
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--type", choices=["text", "icon"])
    p.add_argument("--max-turns", type=int, default=5)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_evaluation(args)
