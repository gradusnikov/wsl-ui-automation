#!/usr/bin/env python3
"""ScreenSpot benchmark evaluation for WSL UI Automation toolkit.

Evaluates how well OCR (find_text) and YOLO (detect) can ground natural
language instructions to correct UI elements on desktop screenshots.

The ScreenSpot benchmark provides:
  - A screenshot image
  - A natural language instruction (e.g., "minimize this window")
  - A ground truth bounding box [x, y, w, h] for the target element
  - Element type: "text" (labels, menus) or "icon" (buttons, controls)

Success = predicted click point falls inside the ground truth bbox.

Usage:
  python eval_screenspot.py                       Run full desktop evaluation
  python eval_screenspot.py --limit 20            Quick test with 20 entries
  python eval_screenspot.py --type text           Text entries only
  python eval_screenspot.py --type icon           Icon entries only
  python eval_screenspot.py --vis                 Save failure visualizations
  python eval_screenspot.py --strategies all      Test all matching strategies
  python eval_screenspot.py --no-yolo             Skip YOLO (OCR only)

Requires servers running:
  find_text --start    (OCR server on :18200)
  detect --start       (YOLO server on :18201)
"""
import sys
import os
import json
import time
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# --- Configuration ---

SCREENSPOT_DIR = Path(os.environ.get(
    "SCREENSPOT_DIR",
    os.path.expanduser("~/devel/ScreenSpot")
))
DATASET_FILE = SCREENSPOT_DIR / "screenspot_desktop.json"
IMAGES_DIR = SCREENSPOT_DIR / "screenspot_imgs"
RESULTS_DIR = Path(__file__).parent / "results"

OCR_URL = "http://127.0.0.1:18200"
YOLO_URL = "http://127.0.0.1:18201"

# Words to strip from instructions before matching (articles, verbs, etc.)
STOP_WORDS = {
    "the", "a", "an", "this", "that", "these", "those",
    "to", "for", "of", "in", "on", "at", "by", "with",
    "is", "are", "was", "were", "be", "been",
    "and", "or", "but", "not", "no",
    "i", "my", "me", "it", "its",
}

# Instruction verbs to strip (action words that aren't on the UI element)
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


# --- Data structures ---

@dataclass
class Prediction:
    """A predicted click point from a strategy."""
    x: int
    y: int
    score: float
    method: str  # "ocr" or "yolo"
    matched_text: str = ""


@dataclass
class EvalResult:
    """Result for a single benchmark entry."""
    index: int
    instruction: str
    data_type: str
    data_source: str
    img_filename: str
    gt_bbox: list
    predictions: dict = field(default_factory=dict)  # strategy -> Prediction | None
    hits: dict = field(default_factory=dict)          # strategy -> bool


@dataclass
class StrategyStats:
    """Aggregate stats for a strategy."""
    total: int = 0
    hits: int = 0
    misses: int = 0
    no_prediction: int = 0

    @property
    def accuracy(self):
        return self.hits / self.total if self.total else 0.0

    @property
    def recall(self):
        """Accuracy among entries where a prediction was made."""
        predicted = self.total - self.no_prediction
        return self.hits / predicted if predicted else 0.0


# --- Server communication ---

def server_health(url):
    try:
        req = urllib.request.Request(f"{url}/health", method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        return resp.status == 200
    except Exception:
        return False


def ocr_image(image_path):
    """Send image to OCR server, return list of text regions."""
    with open(image_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{OCR_URL}/ocr",
        data=data,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())


def yolo_detect(image_path, classes, conf=0.1):
    """Send image to YOLO server with class names, return detections."""
    with open(image_path, "rb") as f:
        data = f.read()
    class_str = ",".join(classes)
    params = urllib.parse.urlencode({"classes": class_str, "conf": conf, "mode": "world"})
    req = urllib.request.Request(
        f"{YOLO_URL}/detect?{params}",
        data=data,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())


# --- Matching functions ---

def fuzzy_match(query, text, case_sensitive=False):
    """Same fuzzy matching as find_text. Returns score 0-1."""
    if not case_sensitive:
        query = query.lower()
        text = text.lower()

    if query == text:
        return 1.0
    if query in text:
        return 0.9 * (len(query) / len(text))
    if text in query:
        return 0.8 * (len(text) / len(query))

    # Word-level: all query words present in text
    qwords = query.split()
    twords = text.split()
    if len(qwords) > 1 and all(any(qw in tw for tw in twords) for qw in qwords):
        return 0.7

    return 0.0


def extract_keywords(instruction):
    """Extract content words from a natural language instruction."""
    words = instruction.lower().strip().split()
    keywords = [w for w in words if w not in STOP_WORDS and w not in ACTION_VERBS and len(w) > 1]
    if not keywords:
        # If all words were stripped, keep non-stop words
        keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    if not keywords:
        keywords = [w for w in words if len(w) > 1]
    return keywords


def extract_target_noun(instruction):
    """Extract the likely target noun phrase from an instruction.

    E.g., "minimize this window" -> "window"
          "open the gallery" -> "gallery"
          "check hourly weather" -> "hourly weather"
    """
    words = instruction.lower().strip().split()
    # Drop leading action verbs and articles
    while words and (words[0] in ACTION_VERBS or words[0] in STOP_WORDS):
        words = words[1:]
    return " ".join(words) if words else instruction.lower()


def point_in_bbox(px, py, bbox):
    """Check if point (px, py) is inside bbox [x, y, w, h]."""
    bx, by, bw, bh = bbox
    return bx <= px <= bx + bw and by <= py <= by + bh


def bbox_center(bbox):
    """Return center point of bbox [x, y, w, h]."""
    return bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2


# --- Matching strategies ---

def strategy_ocr_direct(instruction, ocr_regions):
    """Strategy 1: Direct fuzzy match of full instruction against OCR text.
    This is what find_text does by default."""
    best_score = 0.0
    best_region = None
    for region in ocr_regions:
        score = fuzzy_match(instruction, region["text"])
        if score > best_score:
            best_score = score
            best_region = region
    if best_region and best_score > 0:
        cx, cy = best_region["center"]
        return Prediction(cx, cy, best_score, "ocr", best_region["text"])
    return None


def strategy_ocr_keywords(instruction, ocr_regions):
    """Strategy 2: Extract keywords from instruction, match each against OCR.
    Picks the keyword with the best single-region match."""
    keywords = extract_keywords(instruction)
    best_score = 0.0
    best_region = None
    for kw in keywords:
        for region in ocr_regions:
            score = fuzzy_match(kw, region["text"])
            # Boost score for longer keyword matches
            score *= min(1.0, len(kw) / 4)
            if score > best_score:
                best_score = score
                best_region = region
    if best_region and best_score > 0:
        cx, cy = best_region["center"]
        return Prediction(cx, cy, best_score, "ocr", best_region["text"])
    return None


def strategy_ocr_reverse(instruction, ocr_regions):
    """Strategy 3: Check if OCR text appears as substring of instruction.
    Handles cases like instruction='help menu' where 'Help' appears on screen."""
    instr_lower = instruction.lower()
    best_score = 0.0
    best_region = None
    for region in ocr_regions:
        text = region["text"].lower().strip()
        if len(text) < 2:
            continue
        if text in instr_lower:
            score = len(text) / len(instr_lower)
            if score > best_score:
                best_score = score
                best_region = region
        else:
            # Try each word of the OCR text
            for word in text.split():
                if len(word) >= 3 and word in instr_lower:
                    score = len(word) / len(instr_lower) * 0.8
                    if score > best_score:
                        best_score = score
                        best_region = region
    if best_region and best_score > 0:
        cx, cy = best_region["center"]
        return Prediction(cx, cy, best_score, "ocr", best_region["text"])
    return None


def strategy_ocr_target_noun(instruction, ocr_regions):
    """Strategy 4: Extract target noun phrase and match.
    E.g., 'open the gallery' -> search for 'gallery'."""
    target = extract_target_noun(instruction)
    if not target:
        return None
    best_score = 0.0
    best_region = None
    for region in ocr_regions:
        score = fuzzy_match(target, region["text"])
        if score > best_score:
            best_score = score
            best_region = region
    if best_region and best_score > 0:
        cx, cy = best_region["center"]
        return Prediction(cx, cy, best_score, "ocr", best_region["text"])
    return None


def strategy_ocr_best(instruction, ocr_regions):
    """Strategy 5: Best of all OCR strategies.
    Runs all OCR strategies. Picks by: direct > target_noun > reverse > keywords,
    falling through to next if no prediction. This avoids comparing scores
    across strategies (which use different scales)."""
    priority_order = [
        strategy_ocr_direct,
        strategy_ocr_target_noun,
        strategy_ocr_reverse,
        strategy_ocr_keywords,
    ]
    for strat_fn in priority_order:
        pred = strat_fn(instruction, ocr_regions)
        if pred and pred.score >= 0.4:
            return pred
    # Fall back to any prediction
    for strat_fn in priority_order:
        pred = strat_fn(instruction, ocr_regions)
        if pred:
            return pred
    return None


def strategy_yolo_instruction(instruction, image_path):
    """Strategy 6: Use YOLO-World with instruction-derived class names."""
    target = extract_target_noun(instruction)
    keywords = extract_keywords(instruction)

    # Build class list: full target + individual keywords
    classes = []
    if target:
        classes.append(target)
    classes.extend(keywords)
    # Add the raw instruction too
    classes.append(instruction.lower())
    # Deduplicate preserving order
    seen = set()
    unique_classes = []
    for c in classes:
        if c not in seen:
            seen.add(c)
            unique_classes.append(c)

    if not unique_classes:
        return None

    try:
        detections = yolo_detect(image_path, unique_classes, conf=0.05)
    except Exception as e:
        print(f"  YOLO error: {e}", file=sys.stderr)
        return None

    if not detections:
        return None

    best = detections[0]  # Already sorted by confidence
    cx, cy = best["center"]
    return Prediction(cx, cy, best["confidence"], "yolo", best["class"])


def strategy_combined(instruction, ocr_regions, image_path, use_yolo=True):
    """Strategy 7: OCR best + YOLO fallback.
    Try OCR first; if no match or low confidence, try YOLO."""
    ocr_pred = strategy_ocr_best(instruction, ocr_regions)
    if ocr_pred and ocr_pred.score >= 0.5:
        return ocr_pred

    if use_yolo:
        yolo_pred = strategy_yolo_instruction(instruction, image_path)
        if yolo_pred:
            if ocr_pred is None or yolo_pred.score > ocr_pred.score:
                return yolo_pred

    return ocr_pred


# --- Visualization ---

def save_failure_vis(image_path, gt_bbox, predictions, output_path):
    """Draw ground truth bbox and prediction points on the image."""
    try:
        import cv2
    except ImportError:
        return

    img = cv2.imread(str(image_path))
    if img is None:
        return

    # Ground truth in green
    bx, by, bw, bh = gt_bbox
    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
    gcx, gcy = bbox_center(gt_bbox)
    cv2.drawMarker(img, (gcx, gcy), (0, 255, 0), cv2.MARKER_CROSS, 15, 2)

    # Predictions in different colors
    colors = {
        "ocr_direct": (0, 0, 255),      # red
        "ocr_keywords": (255, 0, 0),     # blue
        "ocr_reverse": (255, 255, 0),    # cyan
        "ocr_target_noun": (0, 255, 255),# yellow
        "ocr_best": (255, 0, 255),       # magenta
        "yolo": (0, 165, 255),           # orange
        "combined": (255, 255, 255),     # white
    }
    for strategy_name, pred in predictions.items():
        if pred is None:
            continue
        color = colors.get(strategy_name, (200, 200, 200))
        cv2.circle(img, (pred.x, pred.y), 8, color, 2)
        cv2.putText(img, strategy_name[:8], (pred.x + 10, pred.y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    cv2.imwrite(str(output_path), img)


# --- Main evaluation ---

OCR_STRATEGIES = {
    "ocr_direct": strategy_ocr_direct,
    "ocr_keywords": strategy_ocr_keywords,
    "ocr_reverse": strategy_ocr_reverse,
    "ocr_target_noun": strategy_ocr_target_noun,
    "ocr_best": strategy_ocr_best,
}


def run_evaluation(args):
    # Load dataset
    with open(DATASET_FILE) as f:
        dataset = json.load(f)

    # Filter by type if requested
    if args.type:
        dataset = [e for e in dataset if e["data_type"] == args.type]

    if args.limit:
        dataset = dataset[:args.limit]

    print(f"ScreenSpot Desktop Benchmark")
    print(f"{'=' * 60}")
    print(f"Entries: {len(dataset)}")
    type_counts = defaultdict(int)
    source_counts = defaultdict(int)
    for e in dataset:
        type_counts[e["data_type"]] += 1
        source_counts[e["data_source"]] += 1
    print(f"Types:   {dict(type_counts)}")
    print(f"Sources: {dict(source_counts)}")
    print()

    # Check servers
    ocr_ok = server_health(OCR_URL)
    yolo_ok = server_health(YOLO_URL) if not args.no_yolo else False
    print(f"OCR server:  {'OK' if ocr_ok else 'NOT RUNNING'}")
    print(f"YOLO server: {'OK' if yolo_ok else 'NOT RUNNING / SKIPPED'}")
    if not ocr_ok:
        print("\nERROR: OCR server required. Start with: find_text --start")
        sys.exit(1)
    print()

    # Determine strategies to run
    strategies = list(args.strategies)
    use_yolo = yolo_ok and not args.no_yolo

    # Initialize stats
    stats = {s: StrategyStats() for s in strategies}
    # Breakdown stats
    stats_by_type = {t: {s: StrategyStats() for s in strategies}
                     for t in ["text", "icon"]}
    stats_by_source = {src: {s: StrategyStats() for s in strategies}
                       for src in set(e["data_source"] for e in dataset)}

    results = []
    ocr_cache = {}  # image_filename -> ocr_regions (many entries share images)

    if args.vis:
        vis_dir = RESULTS_DIR / "vis"
        vis_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    for i, entry in enumerate(dataset):
        img_file = IMAGES_DIR / entry["img_filename"]
        instruction = entry["instruction"].strip()
        gt_bbox = entry["bbox"]
        data_type = entry["data_type"]
        data_source = entry["data_source"]

        if not img_file.exists():
            print(f"  [{i+1}] SKIP - image not found: {entry['img_filename']}")
            continue

        # Progress
        if (i + 1) % 10 == 0 or i == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i+1}/{len(dataset)}] {rate:.1f} entries/sec ...",
                  file=sys.stderr, end="\r")

        # Get OCR results (cached per image)
        img_key = entry["img_filename"]
        if img_key not in ocr_cache:
            try:
                ocr_cache[img_key] = ocr_image(str(img_file))
            except Exception as e:
                print(f"  [{i+1}] OCR error: {e}", file=sys.stderr)
                ocr_cache[img_key] = []
        ocr_regions = ocr_cache[img_key]

        # Run each strategy
        result = EvalResult(
            index=i, instruction=instruction, data_type=data_type,
            data_source=data_source, img_filename=entry["img_filename"],
            gt_bbox=gt_bbox,
        )

        for strat_name in strategies:
            if strat_name in OCR_STRATEGIES:
                pred = OCR_STRATEGIES[strat_name](instruction, ocr_regions)
            elif strat_name == "yolo" and use_yolo:
                pred = strategy_yolo_instruction(instruction, str(img_file))
            elif strat_name == "combined":
                pred = strategy_combined(instruction, ocr_regions,
                                         str(img_file), use_yolo=use_yolo)
            else:
                pred = None

            result.predictions[strat_name] = pred

            hit = False
            if pred:
                hit = point_in_bbox(pred.x, pred.y, gt_bbox)

            result.hits[strat_name] = hit

            # Update stats
            stats[strat_name].total += 1
            stats_by_type[data_type][strat_name].total += 1
            stats_by_source[data_source][strat_name].total += 1

            if pred is None:
                stats[strat_name].no_prediction += 1
                stats_by_type[data_type][strat_name].no_prediction += 1
                stats_by_source[data_source][strat_name].no_prediction += 1
            elif hit:
                stats[strat_name].hits += 1
                stats_by_type[data_type][strat_name].hits += 1
                stats_by_source[data_source][strat_name].hits += 1
            else:
                stats[strat_name].misses += 1
                stats_by_type[data_type][strat_name].misses += 1
                stats_by_source[data_source][strat_name].misses += 1

        results.append(result)

        # Save failure vis for combined/ocr_best
        if args.vis:
            vis_strat = "combined" if "combined" in strategies else "ocr_best"
            if vis_strat in result.hits and not result.hits[vis_strat]:
                vis_path = vis_dir / f"fail_{i:04d}_{data_type}.png"
                save_failure_vis(img_file, gt_bbox, result.predictions, vis_path)

    elapsed = time.time() - t0
    print(f"\n\nCompleted in {elapsed:.1f}s ({len(dataset)/elapsed:.1f} entries/sec)")
    print()

    # --- Print results ---
    print(f"{'=' * 72}")
    print(f"RESULTS — Overall")
    print(f"{'=' * 72}")
    print(f"{'Strategy':<20} {'Accuracy':>10} {'Hits':>6} {'Miss':>6} {'NoPred':>6} {'Recall':>10}")
    print(f"{'-' * 72}")
    for s in strategies:
        st = stats[s]
        print(f"{s:<20} {st.accuracy:>9.1%} {st.hits:>6} {st.misses:>6} "
              f"{st.no_prediction:>6} {st.recall:>9.1%}")
    print()

    # By data_type
    for dtype in ["text", "icon"]:
        subset = stats_by_type.get(dtype, {})
        if not subset or not any(subset[s].total for s in strategies):
            continue
        print(f"{'=' * 72}")
        print(f"RESULTS — {dtype.upper()} elements")
        print(f"{'=' * 72}")
        print(f"{'Strategy':<20} {'Accuracy':>10} {'Hits':>6} {'Miss':>6} {'NoPred':>6} {'Recall':>10}")
        print(f"{'-' * 72}")
        for s in strategies:
            st = subset[s]
            if st.total == 0:
                continue
            print(f"{s:<20} {st.accuracy:>9.1%} {st.hits:>6} {st.misses:>6} "
                  f"{st.no_prediction:>6} {st.recall:>9.1%}")
        print()

    # By data_source
    print(f"{'=' * 72}")
    print(f"RESULTS — By source (best strategy: {'combined' if 'combined' in strategies else strategies[-1]})")
    print(f"{'=' * 72}")
    best_strat = "combined" if "combined" in strategies else strategies[-1]
    print(f"{'Source':<15} {'Accuracy':>10} {'Hits':>6} {'Total':>6}")
    print(f"{'-' * 45}")
    for source in sorted(stats_by_source.keys()):
        st = stats_by_source[source][best_strat]
        if st.total == 0:
            continue
        print(f"{source:<15} {st.accuracy:>9.1%} {st.hits:>6} {st.total:>6}")
    print()

    # --- Save detailed results ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_file = RESULTS_DIR / "screenspot_desktop_results.json"

    output = {
        "benchmark": "ScreenSpot Desktop",
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "toolkit": "WSL UI Automation (OCR: EasyOCR, YOLO: YOLOv8s-World)",
        "total_entries": len(dataset),
        "elapsed_seconds": round(elapsed, 1),
        "strategies": strategies,
        "summary": {
            s: {
                "accuracy": round(stats[s].accuracy, 4),
                "recall": round(stats[s].recall, 4),
                "hits": stats[s].hits,
                "misses": stats[s].misses,
                "no_prediction": stats[s].no_prediction,
                "total": stats[s].total,
            } for s in strategies
        },
        "by_type": {
            dtype: {
                s: {
                    "accuracy": round(stats_by_type[dtype][s].accuracy, 4),
                    "hits": stats_by_type[dtype][s].hits,
                    "total": stats_by_type[dtype][s].total,
                } for s in strategies if stats_by_type[dtype][s].total > 0
            } for dtype in ["text", "icon"]
        },
        "by_source": {
            src: {
                best_strat: {
                    "accuracy": round(stats_by_source[src][best_strat].accuracy, 4),
                    "hits": stats_by_source[src][best_strat].hits,
                    "total": stats_by_source[src][best_strat].total,
                }
            } for src in sorted(stats_by_source.keys())
            if stats_by_source[src][best_strat].total > 0
        },
        "entries": [
            {
                "index": r.index,
                "instruction": r.instruction,
                "data_type": r.data_type,
                "data_source": r.data_source,
                "img_filename": r.img_filename,
                "gt_bbox": r.gt_bbox,
                "gt_center": list(bbox_center(r.gt_bbox)),
                "predictions": {
                    s: {
                        "x": p.x, "y": p.y,
                        "score": round(p.score, 3),
                        "method": p.method,
                        "matched": p.matched_text,
                        "hit": r.hits[s],
                    } if (p := r.predictions.get(s)) else {"hit": False, "no_prediction": True}
                    for s in strategies
                },
            }
            for r in results
        ],
    }

    with open(results_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Detailed results saved to: {results_file}")

    # --- Print sample failures for inspection ---
    best_strat = "combined" if "combined" in strategies else "ocr_best"
    failures = [r for r in results if not r.hits.get(best_strat, False)]
    if failures:
        print(f"\nSample failures ({best_strat}):")
        print(f"{'-' * 72}")
        for r in failures[:15]:
            pred = r.predictions.get(best_strat)
            pred_info = f"-> ({pred.x},{pred.y}) matched='{pred.matched_text}'" if pred else "-> NO PREDICTION"
            print(f"  [{r.data_type:4s}] '{r.instruction}' {pred_info}")
            print(f"         gt_bbox={r.gt_bbox}  gt_center={list(bbox_center(r.gt_bbox))}")


def parse_args():
    parser = argparse.ArgumentParser(description="ScreenSpot benchmark evaluation")
    parser.add_argument("--limit", type=int, help="Limit number of entries to evaluate")
    parser.add_argument("--type", choices=["text", "icon"], help="Filter by element type")
    parser.add_argument("--strategies", nargs="+",
                        default=["ocr_direct", "ocr_keywords", "ocr_reverse",
                                 "ocr_target_noun", "ocr_best", "combined"],
                        help="Strategies to evaluate (default: all)")
    parser.add_argument("--no-yolo", action="store_true",
                        help="Skip YOLO-based strategies")
    parser.add_argument("--vis", action="store_true",
                        help="Save visualizations of failures")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_evaluation(args)
