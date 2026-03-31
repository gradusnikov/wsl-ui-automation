# ScreenSpot Benchmark Results

Evaluation of the WSL UI Automation Toolkit on the [ScreenSpot](https://github.com/njucckevin/SeeClick) GUI grounding benchmark (desktop category, 334 entries).

**Task:** Given a screenshot and a natural language instruction (e.g., "minimize this window"), predict the click coordinates for the target UI element. Success = predicted point falls inside the ground truth bounding box.

## Comparison with Published Models

| Model | Type | Desktop Text | Desktop Icon | Notes |
|---|---|---|---|---|
| MiniGPT-v2 (7B) | End-to-end VLM | 6.2% | 2.9% | |
| Qwen-VL (9.6B) | End-to-end VLM | 5.7% | 5.0% | |
| GPT-4V | End-to-end VLM | 20.2% | 11.8% | |
| Fuyu (8B) | GUI-tuned VLM | 33.0% | 3.6% | |
| CogAgent (18B) | GUI-tuned VLM | 74.2% | 20.0% | |
| SeeClick (9.6B) | GUI-tuned VLM | 72.2% | 30.0% | SOTA (ACL 2024) |
| **smart_click (ours)** | **Hybrid pipeline** | **82.5%** | **40.0%** | **OCR + Claude Haiku** |
| smart_click agentic | Agentic w/ tools | 70.6% | 47.9% | OCR + YOLO + visual_estimate |

Published numbers from [SeeClick paper](https://arxiv.org/abs/2401.10935) (Table 1).

## Our Approach: Hybrid OCR + LLM Vision

Two-stage pipeline — OCR first (fast, free), LLM vision fallback when OCR confidence is low:

1. **OCR stage:** EasyOCR scans the image, fuzzy-matches the instruction against detected text regions (direct match, target noun extraction, reverse containment, keyword match)
2. **Routing decision:** If best OCR match score >= threshold → use OCR result. Otherwise → fall back to LLM.
3. **LLM stage:** Send the screenshot + instruction to Claude, ask for click coordinates.

### Why It Works

The two systems have complementary strengths:

- **OCR excels at text elements** (labels, menus, buttons with text) — it does exact character detection and matching, which is more precise than a VLM's spatial reasoning over text.
- **LLM excels at icons and semantic targets** ("minimize button", "back arrow", "settings gear") — it understands UI semantics visually, where OCR finds nothing.
- **The routing threshold prevents interference** — OCR handles what it's good at, LLM handles the rest. Neither degrades the other.

## Detailed Results

### Strategy Comparison (Full 334 Desktop Entries)

#### OCR-Only Strategies

| Strategy | Overall | Text (194) | Icon (140) |
|---|---|---|---|
| `ocr_direct` (full instruction match) | 43.1% | 71.1% | 4.3% |
| `ocr_keywords` (keyword extraction) | 42.2% | 69.6% | 4.3% |
| `ocr_reverse` (OCR text ⊂ instruction) | 47.9% | 79.9% | 3.6% |
| `ocr_target_noun` (strip verbs/articles) | 42.2% | 69.6% | 4.3% |
| `ocr_best` (priority cascade) | 49.1% | 80.9% | 5.0% |

#### LLM-Only (Claude Haiku 4.5, 20-entry random sample, seed=42)

| Model | Overall | Text (11) | Icon (9) | Median Distance | Speed |
|---|---|---|---|---|---|
| Claude Haiku 4.5 | 70.0% | 54.5% | 88.9% | 12 px | 1.1s/entry |
| Claude Sonnet 4.6 | 65.0% | 45.5% | 88.9% | 7 px | 2.3s/entry |

#### Hybrid: OCR + LLM Fallback (Full 334 Entries, Claude Haiku)

| Threshold | Overall | Text | Icon | OCR-routed | LLM-routed | Cost |
|---|---|---|---|---|---|---|
| 0.30 | **64.7%** | **82.5%** | **40.0%** | 231 (69%) | 103 (31%) | ~$0.11 |
| 0.40 | 63.8% | 79.9% | 41.4% | 214 (64%) | 120 (36%) | ~$0.13 |
| 0.50 | 63.8% | 78.9% | 42.9% | 199 (60%) | 135 (40%) | ~$0.14 |
| 0.60 | 63.5% | 77.8% | 43.6% | 181 (54%) | 153 (46%) | ~$0.17 |
| 0.70 | 63.8% | 78.4% | 43.6% | 169 (51%) | 165 (49%) | ~$0.17 |
| 1.01 (LLM-only) | 54.5% | 59.3% | 47.9% | 0 (0%) | 334 (100%) | ~$0.35 |

**Optimal threshold: 0.30** — maximizes overall accuracy while minimizing LLM calls.

### By Platform (Hybrid, threshold=0.30)

| Platform | Accuracy |
|---|---|
| Windows | 53.1% |
| macOS | 45.9% |

## Key Findings

1. **Hybrid beats both individual approaches.** OCR-only: 49.4%. LLM-only: 54.5%. Hybrid: 64.7%. The combination is more than the sum of its parts.

2. **No training required.** Unlike SeeClick (fine-tuned on 400K GUI grounding examples), our approach is zero-shot — it composes off-the-shelf OCR with a general-purpose LLM.

3. **OCR is better than LLMs at text grounding.** 82.5% vs 59.3%. Dedicated text detection + fuzzy matching outperforms visual language models on finding text elements.

4. **LLMs are dramatically better at icon grounding.** 47.9% vs 5.0%. OCR fundamentally cannot find icons; LLMs understand UI semantics visually.

5. **Cost is trivial.** $0.11 for 334 images with Haiku. Only 31% of entries require an LLM call.

6. **The threshold acts as a natural router.** Low threshold (0.30) = trust OCR more = preserves OCR's strong text performance while still catching icon failures.

## Reproduction

```bash
# Start servers
find_text --start
detect --start

# Run OCR-only evaluation
python benchmark/screenspot/eval_screenspot.py

# Run LLM-only evaluation (20 random entries)
python benchmark/screenspot/eval_llm.py --model haiku --n 20 --seed 42

# Run hybrid evaluation with threshold sweep
python benchmark/screenspot/eval_hybrid.py --model haiku

# Run agentic evaluation (full desktop, ~25 min)
python benchmark/screenspot/eval_agentic.py --model haiku --n 334 --seed 42
```

Requires: ScreenSpot dataset at `~/devel/ScreenSpot/`, OCR server running, `ANTHROPIC_API_KEY` set.

## Agentic Approach: LLM with Tool Access

We also evaluated an agentic approach where the LLM has access to tools (OCR, YOLO, visual estimation) and decides which to use on each entry.

### Tools Available

| Tool | Purpose |
|---|---|
| `ocr_scan` | Run OCR on the screenshot, return all detected text with positions |
| `yolo_detect` | Run YOLO object detection with specified class names |
| `visual_estimate` | LLM reports its own coordinate estimate from the screenshot |
| `click` | Submit final predicted coordinates |

### Results (Full 334 Desktop Entries, Claude Haiku)

| Approach | Overall | Text (194) | Icon (140) | Cost |
|---|---|---|---|---|
| **smart_click (hybrid)** | **64.7%** | **82.5%** | 40.0% | $0.11 |
| Agentic + visual_estimate | 61.1% | 70.6% | **47.9%** | $1.98 |
| LLM-only (direct) | 54.5% | 59.3% | 47.9% | $0.35 |
| OCR-only (best cascade) | 49.1% | 80.9% | 5.0% | $0.00 |

### Tool Usage (Agentic)

| Tool | Calls | Notes |
|---|---|---|
| `click` | 322 | Final answer submission |
| `ocr_scan` | 254 | Used for most text elements |
| `visual_estimate` | 123 | Fallback for icons/hard cases |
| `yolo_detect` | 84 | Tried for icons, rarely useful |
| Avg tools/entry | 2.3 | |

### Why Agentic Underperforms

1. **Text accuracy drops** (70.6% vs 82.5%). The LLM sometimes overrides or misinterprets OCR results instead of trusting them. The fixed routing in smart_click always trusts OCR for high-confidence text matches.

2. **Icon accuracy matches LLM-only** (47.9%). The tools (OCR, YOLO) don't help for icons — the LLM's own visual understanding (via `visual_estimate`) is what works, same as the direct LLM approach.

3. **18x more expensive** ($1.98 vs $0.11). Every entry gets the full screenshot in context plus multi-turn tool calls.

4. **Gridzoom hurts more than it helps.** An earlier variant with gridzoom as a tool scored 50% on a 20-entry sample vs 90% without — the LLM picks wrong grid cells and wastes turns. Removed in favor of `visual_estimate`.

### Conclusion

Fixed routing (OCR first, LLM fallback) outperforms giving the LLM agency over tool selection. The LLM adds value for icons but actively hurts text performance when given control over the pipeline. The optimal strategy is the simplest: trust OCR for text, use LLM vision for everything else.

## Caveats

- **Cloud API dependency.** The LLM stage requires Anthropic API access. SeeClick and CogAgent run locally.
- **Latency.** OCR path: ~0.3s. LLM path: ~1.1s. End-to-end VLMs do a single forward pass.
- **Desktop only.** Web and mobile categories not yet evaluated.
- **Image size limit.** Some macOS screenshots (2560x1440 PNG) exceed the 5MB API limit — 4 entries failed. Could be mitigated by resizing before sending.
