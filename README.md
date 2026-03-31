# WSL UI Automation Toolkit

A comprehensive GUI automation toolkit for Windows applications from WSL2. Combines low-level input tools (screenshot, mouse, keyboard) with AI-powered vision (OCR, YOLO, SAM) and precision targeting (grid navigation, Set-of-Marks) for intelligent UI interaction.

## Architecture

![Architecture](docs/diagrams/architecture.png)

Three layers, each building on the one below:

| Layer | Tools | Purpose |
|-------|-------|---------|
| **Precision Targeting** | `gridzoom`, `som` | Hierarchical grid navigation, element numbering, SAM refinement |
| **AI Vision** | `smart_click`, `click_text`, `find_text`, `detect`, `read_screen`, `wait_for` | Hybrid OCR+LLM, text interaction, object detection |
| **Windows API** | `screenshot`, `mouse`, `sendkeys`, `winctl` | Direct capture, input, and window management |

### GPU Servers

Three persistent servers eliminate model loading overhead:

```bash
find_text --start              # OCR server :18200 (EasyOCR, ~1.5s/scan)
detect --start                 # YOLO server :18201 (YOLO-World + COCO, ~15ms/detect)
python3 ~/bin/sam_server.py &  # SAM server :18202 (MobileSAM, ~3s/segment)
```

## UI Element Targeting Strategy

The toolkit provides **six levels** of targeting precision, from intelligent to surgical. Always start at Level 1 and escalate only when needed.

![Strategy](docs/diagrams/strategy.png)

### Level 1: smart_click (Hybrid OCR + LLM) — most accurate
For any UI element described in natural language. OCR finds text labels; LLM vision finds icons, buttons, and semantic targets.
```bash
smart_click "Submit" -t chrome             # OCR handles this (~0.3s)
smart_click "minimize this window" -t app  # LLM fallback for icons (~1.5s)
smart_click "settings gear" -t chrome      # LLM understands visual semantics
```

### Level 2: click_text (OCR) — fastest for known text
When you know the exact text label. Pure OCR, no API call needed.
```bash
click_text "Submit" -t chrome              # ~2s, pixel-perfect
click_text "Username" -t chrome --offset 200,0  # click input right of label
```

### Level 4: detect (YOLO) — object detection
For visual objects without text labels. Open vocabulary — describe what you see.
```bash
detect -t chrome "button,icon"             # ~15ms
detect -t chrome --coco                    # 80 fixed COCO classes
```

### Level 5: som (Set-of-Marks) — enumerate all elements
When you need to see everything at once. OCR detects all text elements, numbers them, you pick by ID.
```bash
som mark -t chrome                         # detect + annotate + list
som click 17 -t chrome                     # click marker #17
```

### Level 6: gridzoom (Grid Navigation) — hierarchical precision
For elements that OCR/YOLO can't detect. Single capture, pure image manipulation zooms, chess-style coordinates.
```bash
gridzoom capture -t chrome                 # one hi-res grab
gridzoom zoom D4                           # 3x3 crop around D4
gridzoom click B5 -t chrome                # resolve + click
gridzoom refine B5 -t chrome               # SAM segment → exact centroid → click
```

## gridzoom — Hierarchical Visual Navigation

![gridzoom Flow](docs/diagrams/gridzoom_flow.png)

### Core Concept

1. **One capture** — take a single hi-res screenshot of the window
2. **Zoom via image manipulation** — all subsequent "zooms" are crops of the original image (no re-grab)
3. **Depth-aware grid labels** — labels encode zoom depth (`A1` at d=0, `A11` at d=1, `A21` at d=2) so you always know which level you're on
4. **Affine transforms** — the tool tracks scale + offset at each level, maps grid cells back to screen pixels
5. **SAM refinement** — when grid cell centers don't align with element centers, SAM finds the actual object

### Depth-Aware Labels

Cell labels follow the format `{column}{depth}{row}`, where the depth digit is omitted at depth 0. Each depth level has a distinct color:

| Depth | Labels | Grid Color | Example |
|-------|--------|------------|---------|
| 0 | `A1..E5` | Yellow | `gridzoom zoom C3` |
| 1 | `A11..E15` | Cyan | `gridzoom zoom [C12,D12]` |
| 2 | `A21..E25` | Magenta | `gridzoom zoom A23` |
| 3 | `A31..E35` | Green | `gridzoom click B32 -t chrome` |
| 4+ | `A41..E45` | Orange | continues for deeper levels |

This eliminates confusion when navigating multiple zoom levels — seeing `B23` immediately tells you "depth 2, column B, row 3".

### Coordinate Transform

![Transform](docs/diagrams/transform.png)

Each zoom level computes its transform **directly to the original** image — no matrix chain composition, no floating-point drift. Verified to 1px accuracy against OCR ground truth.

### Commands

```bash
gridzoom capture [-t TITLE]       # capture window, overlay grid
gridzoom zoom [ID] CELL           # zoom to single cell
gridzoom zoom [ID] [C1,C2]        # zoom to rectangular region
gridzoom resolve [ID] CELL        # print screen coordinates for cell center
gridzoom click [ID] CELL [-t T]   # resolve + mouse click
gridzoom refine [ID] CELL [-t T]  # SAM segment → centroid → click
gridzoom clean                    # remove session files
```

### Output

Every command produces:
- **Grid image** — with depth-colored labeled markers for cell reference
- **Clean image** — without overlay, for visual inspection
- **Coordinate map** — text table of all cell centers in window coordinates
- **JSON metadata** — affine transform, grid params, depth, parent linkage

## smart_click — Hybrid OCR + LLM Vision

The highest-accuracy targeting tool. Tries OCR first (fast, free), falls back to Claude vision when OCR confidence is low. Beats published GUI grounding models on the ScreenSpot desktop benchmark.

```bash
smart_click "minimize this window" -t app      # auto-routes: OCR or LLM
smart_click "Submit" -t chrome                 # OCR handles text labels
smart_click "settings icon" -t app --verbose   # see routing decision
smart_click "close" --dry-run --json           # find only, structured output
smart_click "upload" --llm-only --model sonnet # force LLM with Sonnet
smart_click "Save" --ocr-only                  # disable LLM (same as click_text)
```

Options: `--threshold` (OCR confidence cutoff, default 0.3), `--model` (haiku/sonnet/opus), `--ocr-only`, `--llm-only`, `--offset`, `--right`, `--double`.

Requires `ANTHROPIC_API_KEY` for LLM fallback.

## Benchmark: ScreenSpot

Evaluated on the [ScreenSpot](https://github.com/njucckevin/SeeClick) GUI grounding benchmark (desktop, 334 entries). Full results in [`benchmark/screenspot/RESULTS.md`](benchmark/screenspot/RESULTS.md).

| Model | Desktop Text | Desktop Icon |
|---|---|---|
| GPT-4V | 20.2% | 11.8% |
| CogAgent (18B) | 74.2% | 20.0% |
| SeeClick (9.6B) | 72.2% | 30.0% |
| **smart_click (ours)** | **82.5%** | **40.0%** |
| smart_click agentic | 70.6% | 47.9% |

Zero-shot hybrid pipeline (EasyOCR + Claude Haiku) outperforms fine-tuned GUI grounding models. Fixed routing (OCR first, LLM fallback at threshold 0.3) beats both agentic tool use and direct LLM approaches. OCR handles text elements with higher precision than VLMs; LLM vision handles icons that OCR cannot see.

## Setup

### Prerequisites
- WSL2 with GPU passthrough (NVIDIA)
- Python 3.10+ with `ultralytics`, `easyocr`, `torch`, `Pillow`
- PowerShell (Windows side, called from WSL)

### Installation

```bash
# Symlink tools to ~/bin/ (must be in PATH)
for f in ~/devel/wsl-ui-automation/bin/*; do
  ln -sf "$f" ~/bin/"$(basename "$f")"
done

# Install Python dependencies
pip install ultralytics easyocr torch torchvision opencv-python Pillow anthropic

# Symlink Claude Code skills (for slash commands)
for f in ~/devel/wsl-ui-automation/skills/*.md; do
  ln -sf "$f" ~/.claude/commands/"$(basename "$f")"
done
```

### Start GPU servers

```bash
find_text --start              # OCR server on :18200
detect --start                 # YOLO server on :18201
python3 ~/bin/sam_server.py &  # SAM server on :18202
```

## Tools Reference

### Low-level: Direct Windows API

| Tool | Purpose | Example |
|------|---------|---------|
| `screenshot` | Capture screen/window | `screenshot /tmp/s.png -t chrome` |
| `mouse` | Click, drag, scroll | `mouse click 500,300 -t chrome` |
| `sendkeys` | Type text, press keys | `sendkeys -t app "hello"` |
| `winctl` | Manage windows | `winctl focus chrome` |

### AI Vision: Hybrid + OCR-powered

| Tool | Purpose | Example |
|------|---------|---------|
| `smart_click` | **Hybrid OCR+LLM** find + click | `smart_click "minimize" -t app` |
| `click_text` | Find text + click (OCR only) | `click_text "Submit" -t chrome` |
| `find_text` | Find text position | `find_text "Search" -t chrome` |
| `wait_for` | Wait for text appear/disappear | `wait_for "Done" -t chrome` |
| `read_screen` | OCR all text on screen | `read_screen -t chrome --text-only` |

### AI Vision: YOLO-powered

| Tool | Purpose | Example |
|------|---------|---------|
| `detect` | Find objects by class name | `detect -t chrome "chair,car"` |
| `detect --coco` | Detect 80 COCO classes | `detect -t chrome --coco` |

### Precision Targeting

| Tool | Purpose | Example |
|------|---------|---------|
| `som mark` | Detect + number all elements | `som mark -t chrome` |
| `som click N` | Click element by number | `som click 17 -t chrome` |
| `gridzoom capture` | Start grid navigation session | `gridzoom capture -t chrome` |
| `gridzoom zoom` | Hierarchical zoom into area | `gridzoom zoom D4` |
| `gridzoom click` | Grid-precise click | `gridzoom click B5 -t chrome` |
| `gridzoom refine` | SAM-refined click | `gridzoom refine B5 -t chrome` |

## Performance

With GPU servers running (RTX 4080):

| Operation | Time | Server |
|-----------|------|--------|
| Screenshot capture | ~0.3s | — |
| **YOLO detection** | **~15ms** | :18201 |
| OCR scan | ~1.5s | :18200 |
| `click_text` end-to-end | ~2s | :18200 |
| `smart_click` (OCR path) | ~2s | :18200 |
| `smart_click` (LLM fallback) | ~2.5s | :18200 + API |
| `som mark` (full page) | ~2s | :18200 |
| `gridzoom capture + zoom` | ~1s | — |
| `gridzoom refine` (SAM) | ~3s | :18202 |

## Claude Code Integration

The `skills/` directory contains Claude Code slash commands:
- `/ui` — unified reference for all tools (updated with gridzoom/som)
- `/screenshot`, `/mouse`, `/sendkeys`, `/winctl` — individual tool skills

Copy to `~/.claude/commands/` to enable.

## Design Decisions

- **Layered targeting strategy**: Start with the simplest tool that works (click_text), escalate only when needed. Each level adds power at the cost of complexity.
- **Single capture, image-only zooms**: gridzoom takes one screenshot and derives all zooms via cropping — no quality loss, no re-grabs, deterministic transforms.
- **Direct-to-original transforms**: Each zoom level computes its affine transform directly to the root image, avoiding floating-point accumulation across chain compositions.
- **SAM as last resort**: MobileSAM segments the actual object boundary when grid cell centers don't align with element centers. Returns the segment centroid — pixel-perfect targeting on any shape.
- **Persistent GPU servers**: Three servers (OCR, YOLO, SAM) stay warm on the GPU. First query pays the model load cost; subsequent queries are fast.
- **Window-relative coordinates**: `--title` flag on all tools makes coordinates independent of window position. PrintWindow API captures even occluded windows.
