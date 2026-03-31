#!/usr/bin/env python3
"""ScreenSpot benchmark: Hybrid OCR + LLM approach.

Routes each entry through a two-stage pipeline:
  1. OCR (fast, free) — try all text-matching strategies
  2. LLM vision (slower, paid) — only when OCR confidence is low

The confidence threshold controls the routing. Sweeps multiple thresholds
to find the optimal trade-off between accuracy and LLM call count.

Usage:
  python eval_hybrid.py                          Full desktop, Haiku fallback
  python eval_hybrid.py --model sonnet           Use Sonnet for fallback
  python eval_hybrid.py --limit 50               First 50 entries
  python eval_hybrid.py --threshold 0.5          Fixed threshold (no sweep)
  python eval_hybrid.py --vis                    Save failure visualizations
"""
import sys
import os
import json
import time
import base64
import re
import struct
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from collections import defaultdict

import anthropic

# --- Configuration ---

SCREENSPOT_DIR = Path(os.environ.get(
    "SCREENSPOT_DIR", os.path.expanduser("~/devel/ScreenSpot")
))
DATASET_FILE = SCREENSPOT_DIR / "screenspot_desktop.json"
IMAGES_DIR = SCREENSPOT_DIR / "screenspot_imgs"
RESULTS_DIR = Path(__file__).parent / "results"

OCR_URL = "http://127.0.0.1:18200"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

SYSTEM_PROMPT = """You are a UI element locator. Given a screenshot and an instruction describing a UI element to interact with, identify the exact pixel coordinates to click.

Output ONLY: CLICK(x, y)
- x = horizontal pixels from left edge
- y = vertical pixels from top edge
- Target the CENTER of the element
- No explanation, just CLICK(x, y)"""

COORD_RE = re.compile(r"CLICK\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)")

STOP_WORDS = {
    "the", "a", "an", "this", "that", "these", "those",
    "to", "for", "of", "in", "on", "at", "by", "with",
    "is", "are", "was", "were", "be", "been",
    "and", "or", "but", "not", "no",
    "i", "my", "me", "it", "its",
}

ACTION_VERBS = {
    "open", "close", "click", "press", "tap", "select", "choose",
    "go", "navigate", "switch", "toggle", "turn", "set", "get",
    "find", "search", "look", "check", "view", "show", "display",
    "enter", "type", "input", "write", "fill",
    "save", "delete", "remove", "add", "create", "new",
    "play", "pause", "stop", "start", "run", "launch",
    "minimize", "maximize", "restore", "resize",
    "copy", "paste", "cut", "undo", "redo",
    "scroll", "drag", "drop", "move",
    "adjust", "change", "modify", "update", "edit",
    "enable", "disable", "activate", "deactivate",
    "expand", "collapse", "fold", "unfold",
    "access", "use", "apply", "submit", "confirm", "cancel",
    "download", "upload", "install", "uninstall",
    "refresh", "reload", "sync",
    "sign", "log", "login", "logout",
}


# --- Geometry helpers ---

def point_in_bbox(px, py, bbox):
    bx, by, bw, bh = bbox
    return bx <= px <= bx + bw and by <= py <= by + bh

def bbox_center(bbox):
    return bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2

def euclidean_dist(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

def get_image_dims(path):
    with open(path, "rb") as f:
        header = f.read(32)
    if header[:4] == b"\x89PNG":
        w, h = struct.unpack(">II", header[16:24])
        return w, h
    import cv2
    img = cv2.imread(str(path))
    return img.shape[1], img.shape[0]


# --- OCR layer ---

def ocr_image(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{OCR_URL}/ocr", data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())


def fuzzy_match(query, text):
    q, t = query.lower(), text.lower()
    if q == t:
        return 1.0
    if q in t:
        return 0.9 * (len(q) / len(t))
    if t in q:
        return 0.8 * (len(t) / len(q))
    qw, tw = q.split(), t.split()
    if len(qw) > 1 and all(any(qw_ in tw_ for tw_ in tw) for qw_ in qw):
        return 0.7
    return 0.0


def extract_keywords(instruction):
    words = instruction.lower().strip().split()
    kw = [w for w in words if w not in STOP_WORDS and w not in ACTION_VERBS and len(w) > 1]
    if not kw:
        kw = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    if not kw:
        kw = [w for w in words if len(w) > 1]
    return kw


def extract_target_noun(instruction):
    words = instruction.lower().strip().split()
    while words and (words[0] in ACTION_VERBS or words[0] in STOP_WORDS):
        words = words[1:]
    return " ".join(words) if words else instruction.lower()


def ocr_find_best(instruction, regions):
    """Run all OCR matching strategies, return (center_x, center_y, confidence) or None.

    Returns the best prediction along with a confidence score that reflects
    how reliably the OCR match can be trusted.
    """
    if not regions:
        return None

    candidates = []

    # Strategy A: direct fuzzy match (full instruction vs each region)
    for r in regions:
        s = fuzzy_match(instruction, r["text"])
        if s > 0:
            candidates.append((r["center"], s, "direct", r["text"]))

    # Strategy B: target noun extraction
    target = extract_target_noun(instruction)
    if target:
        for r in regions:
            s = fuzzy_match(target, r["text"])
            if s > 0:
                candidates.append((r["center"], s, "target_noun", r["text"]))

    # Strategy C: reverse containment (OCR text is substring of instruction)
    instr_lower = instruction.lower()
    for r in regions:
        t = r["text"].lower().strip()
        if len(t) < 2:
            continue
        if t in instr_lower:
            s = len(t) / len(instr_lower)
            candidates.append((r["center"], s, "reverse", r["text"]))
        else:
            for word in t.split():
                if len(word) >= 3 and word in instr_lower:
                    s = len(word) / len(instr_lower) * 0.8
                    candidates.append((r["center"], s, "rev_word", r["text"]))

    # Strategy D: keyword match
    for kw in extract_keywords(instruction):
        for r in regions:
            s = fuzzy_match(kw, r["text"])
            s *= min(1.0, len(kw) / 4)
            if s > 0:
                candidates.append((r["center"], s * 0.9, "keyword", r["text"]))

    if not candidates:
        return None

    # Pick best candidate
    candidates.sort(key=lambda c: c[1], reverse=True)
    center, score, method, matched = candidates[0]
    return {
        "x": center[0], "y": center[1],
        "score": score, "method": f"ocr_{method}", "matched": matched,
    }


# --- LLM layer ---

def llm_find(client, model_id, image_path, instruction, width, height):
    """Ask Claude to locate the UI element. Returns dict or None."""
    with open(image_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    t0 = time.time()
    response = client.messages.create(
        model=model_id,
        max_tokens=100,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                },
                {
                    "type": "text",
                    "text": f"Image: {width}x{height} pixels\nInstruction: {instruction}\nCLICK(x, y):",
                },
            ],
        }],
    )
    reply = response.content[0].text
    latency = time.time() - t0

    m = COORD_RE.search(reply)
    if m:
        return {
            "x": int(m.group(1)), "y": int(m.group(2)),
            "score": 1.0, "method": "llm", "matched": reply.strip(),
            "latency": latency,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    # Fallback: grab any two numbers
    nums = re.findall(r"\b(\d{2,4})\b", reply)
    if len(nums) >= 2:
        return {
            "x": int(nums[0]), "y": int(nums[1]),
            "score": 0.8, "method": "llm_fallback", "matched": reply.strip(),
            "latency": latency,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    return None


# --- Hybrid pipeline ---

def hybrid_find(client, model_id, image_path, instruction, ocr_regions, threshold):
    """Two-stage: OCR first, LLM fallback if OCR confidence < threshold."""
    ocr_result = ocr_find_best(instruction, ocr_regions)

    routed_to = "ocr"
    if ocr_result and ocr_result["score"] >= threshold:
        return ocr_result, routed_to

    # Fall back to LLM
    routed_to = "llm"
    w, h = get_image_dims(str(image_path))
    try:
        llm_result = llm_find(client, model_id, image_path, instruction, w, h)
    except Exception as e:
        print(f"    LLM error: {e}", file=sys.stderr)
        # If LLM fails, return whatever OCR had
        if ocr_result:
            return ocr_result, "ocr_fallback"
        return None, "none"

    if llm_result:
        return llm_result, routed_to

    # LLM returned no coords; use OCR if we had anything
    if ocr_result:
        return ocr_result, "ocr_fallback"
    return None, "none"


# --- Evaluation ---

def run_evaluation(args):
    client = anthropic.Anthropic()
    model_id = MODEL_MAP.get(args.model, args.model)

    with open(DATASET_FILE) as f:
        dataset = json.load(f)

    if args.type:
        dataset = [e for e in dataset if e["data_type"] == args.type]
    if args.limit:
        dataset = dataset[:args.limit]

    total = len(dataset)
    type_counts = defaultdict(int)
    for e in dataset:
        type_counts[e["data_type"]] += 1

    print(f"ScreenSpot Desktop — Hybrid OCR + LLM")
    print(f"{'=' * 70}")
    print(f"Model:     {model_id}")
    print(f"Entries:   {total}")
    print(f"Types:     {dict(type_counts)}")

    # Check OCR server
    try:
        req = urllib.request.Request(f"{OCR_URL}/health", method="GET")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        print("ERROR: OCR server not running. Start with: find_text --start")
        sys.exit(1)

    # Determine thresholds to sweep
    if args.threshold is not None:
        thresholds = [args.threshold]
    else:
        thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]
        # 1.01 = "always LLM" (no OCR score can reach it)

    # Pre-compute all OCR results (cached per image)
    print(f"\nPhase 1: OCR scan ({len(set(e['img_filename'] for e in dataset))} unique images)...")
    ocr_cache = {}
    t_ocr_start = time.time()
    for i, entry in enumerate(dataset):
        img_key = entry["img_filename"]
        if img_key not in ocr_cache:
            img_path = IMAGES_DIR / img_key
            try:
                ocr_cache[img_key] = ocr_image(str(img_path))
            except Exception as e:
                print(f"  OCR error on {img_key}: {e}", file=sys.stderr)
                ocr_cache[img_key] = []
        if (i + 1) % 50 == 0:
            print(f"  OCR: {i+1}/{total}...", file=sys.stderr, end="\r")
    t_ocr = time.time() - t_ocr_start
    print(f"  OCR done in {t_ocr:.1f}s")

    # Pre-compute OCR scores for all entries to know routing decisions
    ocr_scores = []
    for entry in dataset:
        regions = ocr_cache.get(entry["img_filename"], [])
        result = ocr_find_best(entry["instruction"].strip(), regions)
        ocr_scores.append(result["score"] if result else 0.0)

    # Show how many LLM calls each threshold needs
    print(f"\nThreshold sweep — LLM calls needed:")
    for t in thresholds:
        llm_needed = sum(1 for s in ocr_scores if s < t)
        print(f"  threshold={t:.2f}: {llm_needed}/{total} LLM calls "
              f"({llm_needed/total:.0%}), {total - llm_needed} OCR-only")

    # Run the actual hybrid evaluation for each threshold
    # LLM results are cached: call LLM once per entry, reuse across thresholds
    print(f"\nPhase 2: LLM calls for entries below highest threshold...")

    max_threshold = max(thresholds)
    llm_cache = {}  # entry index -> llm result or None
    llm_indices = [i for i, s in enumerate(ocr_scores) if s < max_threshold]
    llm_total = len(llm_indices)
    total_input_tokens = 0
    total_output_tokens = 0

    t_llm_start = time.time()
    for count, idx in enumerate(llm_indices):
        entry = dataset[idx]
        img_path = IMAGES_DIR / entry["img_filename"]
        w, h = get_image_dims(str(img_path))
        instruction = entry["instruction"].strip()

        try:
            result = llm_find(client, model_id, img_path, instruction, w, h)
            llm_cache[idx] = result
            if result:
                total_input_tokens += result.get("input_tokens", 0)
                total_output_tokens += result.get("output_tokens", 0)

            status = f"({result['x']},{result['y']})" if result else "NO_COORDS"
            latency = result.get("latency", 0) if result else 0
            print(f"  [{count+1}/{llm_total}] {entry['data_type']:4s} "
                  f"'{instruction[:35]:<35s}' -> {status}  [{latency:.1f}s]",
                  file=sys.stderr)
        except Exception as e:
            print(f"  [{count+1}/{llm_total}] ERROR: {e}", file=sys.stderr)
            llm_cache[idx] = None

    t_llm = time.time() - t_llm_start
    print(f"  LLM done: {llm_total} calls in {t_llm:.1f}s "
          f"({t_llm/llm_total:.1f}s/call)" if llm_total else "  No LLM calls needed")

    # Now evaluate each threshold
    print(f"\n{'=' * 70}")
    print(f"RESULTS")
    print(f"{'=' * 70}")

    all_threshold_results = {}

    for threshold in thresholds:
        hits = 0
        misses = 0
        no_pred = 0
        routed_ocr = 0
        routed_llm = 0
        hits_text = 0
        hits_icon = 0
        total_text = type_counts.get("text", 0)
        total_icon = type_counts.get("icon", 0)
        entries_detail = []

        for i, entry in enumerate(dataset):
            instruction = entry["instruction"].strip()
            gt_bbox = entry["bbox"]
            dtype = entry["data_type"]
            regions = ocr_cache.get(entry["img_filename"], [])

            ocr_result = ocr_find_best(instruction, regions)
            ocr_score = ocr_result["score"] if ocr_result else 0.0

            if ocr_score >= threshold:
                pred = ocr_result
                route = "ocr"
                routed_ocr += 1
            else:
                pred = llm_cache.get(i)
                route = "llm"
                routed_llm += 1

            hit = False
            if pred:
                hit = point_in_bbox(pred["x"], pred["y"], gt_bbox)
                if hit:
                    hits += 1
                    if dtype == "text":
                        hits_text += 1
                    else:
                        hits_icon += 1
                else:
                    misses += 1
            else:
                no_pred += 1

            entries_detail.append({
                "index": i,
                "instruction": instruction,
                "data_type": dtype,
                "gt_bbox": gt_bbox,
                "ocr_score": round(ocr_score, 3),
                "route": route,
                "pred": {"x": pred["x"], "y": pred["y"], "method": pred["method"],
                         "matched": pred.get("matched", "")} if pred else None,
                "hit": hit,
            })

        acc = hits / total if total else 0
        acc_text = hits_text / total_text if total_text else 0
        acc_icon = hits_icon / total_icon if total_icon else 0

        label = f"t={threshold:.2f}"
        if threshold > 1.0:
            label = "LLM-only"
        print(f"  {label:<12s}  acc={acc:5.1%}  text={acc_text:5.1%}  "
              f"icon={acc_icon:5.1%}  ocr={routed_ocr:>3d}  llm={routed_llm:>3d}  "
              f"nopred={no_pred}")

        all_threshold_results[f"{threshold:.2f}"] = {
            "threshold": threshold,
            "accuracy": round(acc, 4),
            "accuracy_text": round(acc_text, 4),
            "accuracy_icon": round(acc_icon, 4),
            "routed_ocr": routed_ocr,
            "routed_llm": routed_llm,
            "no_prediction": no_pred,
            "hits": hits,
            "entries": entries_detail,
        }

    # Print comparison baselines
    print(f"\n  {'Baselines:':<12s}")
    print(f"  {'OCR-only':<12s}  acc=49.4%  text=80.9%  icon= 5.7%  "
          f"(from full eval_screenspot.py run)")

    # Token usage summary
    print(f"\n{'=' * 70}")
    print(f"Cost estimate ({model_id}):")
    print(f"  LLM calls:     {llm_total}")
    print(f"  Input tokens:  {total_input_tokens:,}")
    print(f"  Output tokens: {total_output_tokens:,}")
    if "haiku" in model_id:
        cost = total_input_tokens * 0.80 / 1e6 + total_output_tokens * 4.0 / 1e6
    elif "sonnet" in model_id:
        cost = total_input_tokens * 3.0 / 1e6 + total_output_tokens * 15.0 / 1e6
    else:
        cost = total_input_tokens * 15.0 / 1e6 + total_output_tokens * 75.0 / 1e6
    print(f"  Estimated cost: ${cost:.2f}")
    print(f"  Time: OCR={t_ocr:.1f}s + LLM={t_llm:.1f}s = {t_ocr+t_llm:.1f}s total")

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"hybrid_{args.model}.json"
    output = {
        "benchmark": "ScreenSpot Desktop — Hybrid OCR + LLM",
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "model": model_id,
        "total_entries": total,
        "ocr_time": round(t_ocr, 1),
        "llm_time": round(t_llm, 1),
        "llm_calls": llm_total,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "thresholds": all_threshold_results,
    }
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {out_file}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="haiku", choices=list(MODEL_MAP.keys()))
    p.add_argument("--limit", type=int)
    p.add_argument("--type", choices=["text", "icon"])
    p.add_argument("--threshold", type=float, help="Fixed threshold (skip sweep)")
    p.add_argument("--vis", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_evaluation(args)
