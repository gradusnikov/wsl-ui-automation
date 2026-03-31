---
description: UI automation — interact with Windows GUI apps using som, gridzoom, mouse, sendkeys, and winctl. Use for UI testing, browser automation, clicking buttons, filling forms, or any visual interaction.
---

# UI Automation

You have a full Windows GUI automation toolkit at `~/bin/`. Use it to see, click, type, and manage windows.

## Tools

| Tool | Purpose | Notes |
|---|---|---|
| **smart_click** | **Hybrid OCR + LLM** find + click | **Most accurate** — handles text AND icons |
| **som** | Set-of-Marks: detect + number all elements | See everything, pick by ID |
| **click_text** | OCR + click in one command | Fast, when you know the exact text label |
| **find_text** | OCR: find text position on screen | Returns coordinates for clicking |
| **read_screen** | OCR all text from window | Structured output, position-sorted |
| **wait_for** | Poll until text appears/disappears | For async UI, page loads, spinners |
| **gridzoom** | Hierarchical grid navigation + SAM | Chess coords → pixel-perfect clicks |
| **detect** | YOLO object detection (open vocab) | ~15ms, "find chairs", "find buttons" |
| **mouse** | Move, click, drag, scroll | Window-relative coordinates with `--title` |
| **sendkeys** | Keyboard input (keys and text) | Clipboard paste for text, SendKeys for hotkeys |
| **winctl** | List, focus, min/max/close windows | Title/process substring match |

### GPU servers

Three persistent servers eliminate model loading overhead:

```bash
find_text --start              # OCR server :18200 (~1.5s/scan)
detect --start                 # YOLO server :18201 (~15ms/detect)
python3 ~/bin/sam_server.py &  # SAM server :18202 (~3s/segment)
```

All run on GPU (RTX 4080). **Start servers before interactive sessions.**

## Core workflow: tools-first, not vision-first

**IMPORTANT: Never estimate pixel positions from screenshots. Never use screenshot crops to locate elements. Always use the targeting tools below.**

### Targeting strategy:

1. **Default →** `smart_click "description" -t app` — handles both text and icons via hybrid OCR + LLM. Fastest path from intent to click.
2. **Need UI overview?** → `som mark -t app` — see ALL elements numbered, pick by ID
3. **Know the exact label?** → `click_text "Label" -t app` — pure OCR, no API call, fastest
4. **Element has no text?** → `gridzoom capture -t app` → `gridzoom zoom D4` → `gridzoom click B5 -t app`
5. **Need sub-cell precision?** → `gridzoom refine B5 -t app` — SAM segmentation → exact centroid
6. **Is a known object class?** → `detect -t app "object"` — YOLO, ~15ms

### Do NOT:
- Use `screenshot` — use `som mark` to see the UI (it captures a screenshot internally and gives you both marked + clean images)
- Estimate pixel coordinates visually — always use a tool
- Default to `click_text` for icons/non-text elements — use `smart_click` instead, it falls back to LLM vision

## som — Set-of-Marks

Detects all text elements on screen, numbers them with visual markers. You read the annotated image, pick a number, click it.

```bash
som mark -t chrome                   # detect all text elements, number them
# Read /tmp/som/screen_marked.png to see numbered elements
# Read /tmp/som/screen_clean.png for clean view
som click 17 -t chrome               # click element #17
```

**When to use:** When you need an overview of all clickable elements, or when you're not sure which text label to target.

## gridzoom — Hierarchical Grid Navigation

Single capture, pure image manipulation zooms, chess-style coordinates with affine transform tracking. **Labels encode zoom depth** so you always know which level you're on.

```bash
gridzoom capture -t chrome           # one hi-res grab, 5x5 grid (A1..E5)
gridzoom zoom C3                     # zoom to single cell C3
gridzoom zoom [B2,D4]                # zoom to region B2..D4 (3x3 cells)
gridzoom zoom [A1,E2]                # zoom to top half (5x2 cells)
gridzoom click B3 -t chrome          # resolve cell → click
gridzoom refine B3 -t chrome         # SAM segment → centroid → click (most precise)
gridzoom resolve B3                  # just print screen coordinates
gridzoom clean                       # remove session files
```

**Depth-aware labels:** Cell labels encode the zoom depth so you always know which level you're operating at. Format: `{column}{depth}{row}` — the depth digit is omitted at depth 0.

| Depth | Labels | Color | Example |
|-------|--------|-------|---------|
| 0 | `A1..E5` | Yellow | `gridzoom zoom C3` |
| 1 | `A11..E15` | Cyan | `gridzoom zoom [C12,D12]` |
| 2 | `A21..E25` | Magenta | `gridzoom zoom A23` |
| 3 | `A31..E35` | Green | `gridzoom click B32` |

**Key patterns:**
- **Capture once** per session — grid coords are stable, reuse them for all clicks
- **Range zoom `[X,Y]`** — specify two corner cells to zoom into any rectangular region
- **Read the grid image** to see which cell contains what, then choose your zoom target. The labels on each cell tell you exactly what to reference.
- Zoom produces both `_grid.png` (labeled) and `_clean.png` (raw) — **read grid for cell reference, clean for visual judgment**
- Output includes coordinate map: `A1=129,140  B1=388,140  ...` for every cell
- Use `gridzoom refine` when a grid cell center doesn't land on the target — SAM finds the actual object centroid
- To zoom from a specific parent level (not the latest), pass the image ID: `gridzoom zoom <ID> [B12,D13]`

## Quick reference

### smart_click — MOST ACCURATE tool for clicking UI elements
```bash
smart_click "minimize this window" -t app      # auto-routes: OCR or LLM
smart_click "Submit" -t chrome                 # OCR handles text labels fast
smart_click "settings icon" -t app             # LLM handles icons
smart_click "close" --dry-run --json           # find only, structured output
smart_click "Upload" -t chrome --ocr-only      # no LLM fallback (= click_text)
smart_click "gear icon" --llm-only             # skip OCR, use LLM directly
smart_click "Tab" -t app --offset 0,-20        # offset from element center
smart_click "Save" -t app --model sonnet       # use Sonnet instead of Haiku
```

### click_text — fast OCR-only clicking (no API cost)
```bash
click_text "Search" -t chrome              # find and click text
click_text "Submit" -t chrome --right      # right-click
click_text "Item" -t chrome --double       # double-click
click_text "Tab" -t chrome --offset 0,-20  # click 20px above text center
click_text "Save" -t chrome --index 2      # click 2nd occurrence
click_text "Save" -t chrome --dry-run      # find only, print coordinates
```

### find_text — find text coordinates without clicking
```bash
find_text "Search" -t chrome               # best match: "X,Y  text  bbox=..."
find_text "Search" -t chrome -a            # all matches
find_text --list -t chrome                 # list all detected text
find_text --list -t chrome -j              # JSON output
find_text --start                          # start OCR server
find_text --stop                           # stop OCR server
```

### wait_for — wait for UI state changes
```bash
wait_for "Loading complete" -t chrome      # wait until text appears (15s timeout)
wait_for "Loading..." -t chrome --gone     # wait until text disappears
wait_for "Ready" -t chrome --timeout 30    # custom timeout
```

### read_screen — read all text from UI
```bash
read_screen -t chrome --text-only          # just text, line-grouped
read_screen -t chrome --json               # full JSON with bboxes
```

### mouse
```bash
mouse click 500,300                        # left click (absolute)
mouse click 50,80 -t notepad              # click relative to window
mouse rclick 500,300                       # right click
mouse dclick 200,100                       # double click
mouse drag 100,200 500,300                 # drag from → to
mouse scroll down 5                        # scroll down 5 notches
```

### sendkeys
```bash
sendkeys -t notepad "Hello World"          # type text (clipboard paste)
sendkeys -t chrome --key ctrl+l            # hotkey
sendkeys --key enter                       # single key
sendkeys --keys "tab,tab,enter"            # key sequence
sendkeys -r 5 --key tab                    # repeat key N times
```

### winctl
```bash
winctl list                                # list all visible windows
winctl list chrome                         # filter by title/process
winctl focus notepad                       # bring to foreground
winctl close "Untitled"                    # close window
```

### detect — YOLO object detection
```bash
detect -t chrome "chair,car,person"        # open-vocabulary (YOLO-World)
detect -t chrome --coco                    # 80 COCO classes (~15ms)
detect --start / --stop                    # manage YOLO server
```

## Key patterns

### Targeting windows
All tools support `--title`/`-t` for window targeting (case-insensitive substring match):
```bash
click_text "Search" -t chrome              # OCR + click, window-relative
mouse click 100,200 -t chrome             # coordinates relative to window
som mark -t chrome                        # detect elements in specific window
sendkeys -t notepad "text"                # focuses window then types
```

**Always prefer `--title` over alt-tab.** It's reliable and doesn't depend on focus.

### Browser automation
```bash
sendkeys -t chrome --key ctrl+l && sendkeys -t chrome "https://example.com" && sendkeys -t chrome --key enter
wait_for "expected text" -t chrome
click_text "Sign In" -t chrome
read_screen -t chrome --text-only
```

### Form filling
```bash
click_text "Username" -t chrome --offset 200,0
sendkeys -t chrome "myuser"
sendkeys -t chrome --key tab
sendkeys -t chrome "mypassword"
click_text "Submit" -t chrome
```

### Typical interaction flow
```bash
# Step 1: ALWAYS start with som to understand the UI
som mark -t app
# Read /tmp/som/screen_marked.png — see all numbered elements
# Read /tmp/som/screen_clean.png — clean view for context
som click 23 -t app                        # click by number

# Step 2: if som doesn't detect the target, use gridzoom
gridzoom capture -t app
gridzoom zoom D4                           # zoom to area of interest
# Read the clean image to see what's there
gridzoom click B5 -t app                   # click by grid cell

# Step 3: if grid cell center misses, refine with SAM
gridzoom refine B5 -t app                  # SAM finds exact object centroid
```

## Interpreting the user's request

When the user says `/ui`, parse their intent:

- **"click on X"** → `smart_click "X" -t <app>` — handles text labels AND icons/visual targets
- **"click the icon/button"** → `smart_click "description" -t <app>` — LLM understands icons
- **"read/what's on screen"** → `read_screen -t <app>`
- **"type X into Y"** → `smart_click "Y" -t <app>` to find the field, then `sendkeys -t <app> "X"`
- **"interact with this app"** → `som mark -t <app>` first — see what's there, then act
- **"wait for X"** → `wait_for "X" -t <app>`
- **"scroll down"** → `mouse scroll down -t <app>`
- **"list windows"** → `winctl list`
- **"find the button/icon"** → `smart_click "description" -t <app> --dry-run` — find without clicking

$ARGUMENTS
