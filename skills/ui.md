---
description: UI automation — interact with Windows GUI apps using screenshot, mouse, sendkeys, and winctl. Use for UI testing, browser automation, clicking buttons, filling forms, or any visual interaction.
---

# UI Automation

You have a full Windows GUI automation toolkit at `~/bin/`. Use it to see, click, type, and manage windows.

## Tools

| Tool | Purpose | Notes |
|---|---|---|
| **screenshot** | Capture screen or window | PrintWindow API, works even if occluded |
| **mouse** | Move, click, drag, scroll | Window-relative coordinates with `--title` |
| **sendkeys** | Keyboard input (keys and text) | Clipboard paste for text, SendKeys for hotkeys |
| **winctl** | List, focus, min/max/close windows | Title/process substring match |
| **find_text** | OCR: find text position on screen | Returns coordinates for clicking |
| **click_text** | OCR + click in one command | Best way to click UI elements by label |
| **wait_for** | Poll until text appears/disappears | For async UI, page loads, spinners |
| **read_screen** | OCR all text from window | Structured output, position-sorted |
| **detect** | YOLO object detection (open vocab) | ~15ms, "find chairs", "find buttons" |
| **som** | Set-of-Marks: detect + number all elements | Pick element by ID |
| **gridzoom** | Hierarchical grid navigation + SAM | Chess coords → pixel-perfect clicks |

### GPU servers

Three persistent servers eliminate model loading overhead:

```bash
find_text --start              # OCR server :18200 (~1.5s/scan)
detect --start                 # YOLO server :18201 (~15ms/detect)
python3 ~/bin/sam_server.py &  # SAM server :18202 (~3s/segment)
```

All run on GPU (RTX 4080). **Start servers before interactive sessions.**

## Core workflow: tools-first, not vision-first

**IMPORTANT: Your visual coordinate estimation is unreliable (~50-125px error). Never estimate pixel positions from screenshots. Always use tools for precision.**

### Targeting strategy — from lightweight to precise:

1. **Has text?** → `click_text "Label" -t app` (OCR, ~2s, highest confidence)
2. **Is a known object?** → `detect -t app "object"` (YOLO, ~15ms)
3. **Need to see all elements?** → `som mark -t app` then `som click N -t app` (OCR + numbering)
4. **No text, no detectable object?** → `gridzoom capture -t app` → `gridzoom zoom D4` → `gridzoom click B5 -t app` (grid navigation)
5. **Grid cell not centered on target?** → `gridzoom refine B5 -t app` (SAM segmentation → exact centroid)

### gridzoom quick reference

```bash
gridzoom capture -t chrome           # one hi-res grab, 10x10 grid
gridzoom zoom D4                     # 3x3 window around D4 (default +1 padding)
gridzoom zoom D4+2                   # 5x5 window (wider context)
gridzoom click B5 -t chrome          # resolve cell → click
gridzoom refine B5 -t chrome         # SAM segment → centroid → click
gridzoom resolve B5                  # just print screen coordinates
```

**Key patterns:**
- Capture once per session — grid coords are stable, reuse them for all clicks
- Use `screenshot` for quick peeks between clicks (don't re-capture gridzoom)
- Zoom produces both `_grid.png` (labeled) and `_clean.png` (raw) — read clean for visual judgment, grid for cell reference
- Output includes coordinate map: `A1=65,70  B1=194,70  ...` for every cell

### som quick reference

```bash
som mark -t chrome                   # detect all text elements, number them
som click 17 -t chrome               # click element #17
```

### Do NOT:
- Take a screenshot and try to estimate pixel coordinates from it
- Use `screenshot` when `read_screen` would give you the information you need
- Crop → read → crop → read in loops. Use OCR tools instead.

### Standard interaction patterns:

**Click a button/link:**
```bash
click_text "Submit" -t chrome              # one step, exact coordinates
```

**Read what's on screen:**
```bash
read_screen -t chrome --text-only          # OCR all text, no screenshot needed
```

**Explore an unfamiliar app:**
```bash
read_screen -t app --text-only             # understand the UI via text
click_text "Menu Item" -t app              # navigate by clicking text labels
read_screen -t app --text-only             # read what changed
```

**Click near a label (e.g., input field next to label):**
```bash
click_text "Username" -t chrome --offset 200,0    # click 200px right of label
```

**Visual verification (show user what happened):**
```bash
screenshot /tmp/s.png -t app               # only when user needs to SEE the result
```

## Quick reference

### click_text (`~/bin/click_text`) — PRIMARY tool for clicking UI elements
```bash
click_text "Search" -t chrome              # find and click text
click_text "Submit" -t chrome --right      # right-click
click_text "Item" -t chrome --double       # double-click
click_text "Tab" -t chrome --offset 0,-20  # click 20px above text center
click_text "Save" -t chrome --index 2      # click 2nd occurrence
click_text "Save" -t chrome --dry-run      # find only, print coordinates
```

### find_text (`~/bin/find_text`) — find text coordinates without clicking
```bash
find_text "Search" -t chrome               # best match: "X,Y  text  bbox=..."
find_text "Search" -t chrome -a            # all matches
find_text --list -t chrome                 # list all detected text
find_text --list -t chrome -j              # JSON output
find_text --list -t chrome --vis           # save annotated image with all text boxes
find_text "Search" -t chrome --vis         # annotated image highlighting matches
find_text --start                          # start OCR server
find_text --stop                           # stop OCR server
```

### wait_for (`~/bin/wait_for`) — wait for UI state changes
```bash
wait_for "Loading complete" -t chrome      # wait until text appears (15s timeout)
wait_for "Loading..." -t chrome --gone     # wait until text disappears
wait_for "Ready" -t chrome --timeout 30    # custom timeout
wait_for "Ready" -t chrome --interval 0.5  # poll every 0.5s
```

### read_screen (`~/bin/read_screen`) — read all text from UI
```bash
read_screen -t chrome                      # all text with positions
read_screen -t chrome --text-only          # just text, line-grouped
read_screen -t chrome --json               # full JSON with bboxes
read_screen -t chrome -r 400,500,300,200   # OCR a specific region only
```

### screenshot (`~/bin/screenshot`)
```bash
screenshot /tmp/s.png                      # primary screen
screenshot /tmp/s.png -t chrome            # Chrome window (works even if occluded)
screenshot /tmp/s.png -w                   # focused/foreground window
screenshot /tmp/s.png -a                   # all monitors stitched
screenshot /tmp/s.png -c                   # clipboard image
screenshot /tmp/s.png -t app --crop X,Y,W,H  # capture + crop (post-capture)
screenshot /tmp/s.png --scale 50           # downscale 50%
screenshot /tmp/s.png -d 3 -w             # delay 3s before capture

# Annotations — draw on screenshots to communicate visually
screenshot /tmp/s.png -t app --arrow 100,200,300,150
screenshot /tmp/s.png -t app --circle 500,300,40
screenshot /tmp/s.png -t app --highlight 200,100,400,80
screenshot /tmp/s.png -t app --label 210,90 "Click here"
screenshot /tmp/s.png -t app --color yellow --arrow 0,0,50,50
screenshot /tmp/s.png -t app --grid 100    # coordinate grid overlay
```

### mouse (`~/bin/mouse`)
```bash
mouse pos                                  # current cursor position
mouse click 500,300                        # left click (absolute)
mouse click 50,80 -t notepad              # click relative to window
mouse rclick 500,300                       # right click
mouse dclick 200,100                       # double click
mouse drag 100,200 500,300                 # drag from → to
mouse scroll down 5                        # scroll down 5 notches
mouse scroll up -t chrome                  # scroll up in Chrome
```

### sendkeys (`~/bin/sendkeys`)
```bash
sendkeys -t notepad "Hello World"          # type text (clipboard paste)
sendkeys -t chrome --key ctrl+l            # hotkey
sendkeys --key enter                       # single key
sendkeys --keys "tab,tab,enter"            # key sequence
sendkeys -r 5 --key tab                    # repeat key N times
sendkeys -r 3 -p 500 --key down           # repeat with pause between
```

### winctl (`~/bin/winctl`)
```bash
winctl list                                # list all visible windows
winctl list chrome                         # filter by title/process
winctl focus notepad                       # bring to foreground
winctl minimize chrome                     # minimize
winctl maximize chrome                     # maximize
winctl close "Untitled"                    # close window
```

### detect (`~/bin/detect`) — YOLO object detection
```bash
detect -t chrome                           # detect COCO objects (80 classes, ~15ms)
detect -t chrome "chair,car,person"        # open-vocabulary (YOLO-World)
detect --file image.png "chair" -c 0.3     # detect in file, custom confidence
detect --coco -t chrome                    # force COCO model
detect --list                              # list 80 COCO class names
detect -t chrome --vis                     # save annotated image to /tmp/detect_vis.png
detect --start / --stop                    # manage YOLO server
```

### imgcrop (`~/bin/imgcrop`) — crop images by coords, grid, or detection
```bash
imgcrop image.png 370,540,460,480          # crop by X,Y,W,H
imgcrop image.png --grid 3x3              # print grid cell info
imgcrop image.png --grid 3x3 --cell 1,2   # extract single cell [row,col]
imgcrop image.png --grid 3x3 --all        # save all cells as separate files
imgcrop image.png --detect "chair"         # crop to first YOLO chair detection
imgcrop image.png --detect --coco --all    # crop all COCO detections
imgcrop image.png --ocr "Submit"           # crop to OCR text match
imgcrop image.png --pad 10 ...            # add padding around any crop
```

**When to use what:**
- **OCR** (`click_text`/`find_text`): clicking buttons, reading text — anything with text labels
- **YOLO** (`detect`): finding real-world objects in images (~15ms) — chairs, cars, people, etc.

## Key patterns

### Targeting windows
All tools support `--title`/`-t` for window targeting (case-insensitive substring match):
- `screenshot -t chrome` — captures even if behind other windows
- `mouse click 100,200 -t chrome` — coordinates relative to Chrome's top-left
- `click_text "Search" -t chrome` — OCR + click, window-relative
- `sendkeys -t notepad "text"` — focuses window then types

**Always prefer `--title` over alt-tab.** It's reliable and doesn't depend on focus.

### Browser automation
```bash
# Navigate
sendkeys -t chrome --key ctrl+l && sendkeys -t chrome "https://example.com" && sendkeys -t chrome --key enter
wait_for "expected text" -t chrome                     # wait for page load

# Interact
click_text "Sign In" -t chrome                         # click a button/link
mouse click X,Y -t chrome                              # click by coordinates
sendkeys -t chrome "form value"                        # type into focused field

# Read
read_screen -t chrome --text-only                      # read page text
find_text "Status:" -t chrome                          # find specific text
```

### Form filling pattern
```bash
click_text "Username" -t chrome --offset 200,0         # click input field right of label
sendkeys -t chrome "myuser"
sendkeys -t chrome --key tab                           # next field
sendkeys -t chrome "mypassword"
click_text "Submit" -t chrome
```

### Wait for async operations
```bash
click_text "Save" -t app
wait_for "Saved successfully" -t app --timeout 10
# or
wait_for "Saving..." -t app --gone --timeout 10
```

## Interpreting the user's request

When the user says `/ui`, parse their intent:

- **"click on X"** → `click_text "X" -t <app>`
- **"read/what's on screen"** → `read_screen -t <app>` or `screenshot`
- **"type X into Y"** → `click_text "Y" -t <app>` then `sendkeys -t <app> "X"`
- **"wait for X"** → `wait_for "X" -t <app>`
- **"scroll down"** → `mouse scroll down -t <app>`
- **"list windows"** → `winctl list`
- **Complex multi-step** → chain tools, verify with `read_screen`/`wait_for` after each action

## Workflow examples

### Web search
```bash
click_text "Ask Google" -t chrome                          # click search box
sendkeys -t chrome "weather tomorrow" && sendkeys -t chrome --key enter
wait_for "Results for" -t chrome --timeout 5               # wait for results
read_screen -t chrome --text-only                          # read the answer
```

### Navigate and fill a web form
```bash
sendkeys -t chrome --key ctrl+l                            # focus address bar
sendkeys -t chrome "https://example.com/login" && sendkeys -t chrome --key enter
wait_for "Sign in" -t chrome --timeout 10                  # wait for page load
click_text "Email" -t chrome --offset 200,0                # click input next to label
sendkeys -t chrome "user@example.com"
sendkeys -t chrome --key tab                               # move to next field
sendkeys -t chrome "password123"
click_text "Sign in" -t chrome                             # submit
wait_for "Welcome" -t chrome --timeout 10                  # confirm success
```

### Explore an unfamiliar desktop app
```bash
winctl list                                                # find the app
read_screen -t myapp --text-only                           # read all UI text
click_text "File" -t myapp                                 # open menu
read_screen -t myapp --text-only                           # read menu items
click_text "Settings" -t myapp                             # navigate
read_screen -t myapp --text-only                           # read settings panel
```

### Multi-step with verification
```bash
click_text "Save" -t app
wait_for "Saved" -t app --timeout 10                       # wait for confirmation
# or if no confirmation text:
read_screen -t app --text-only                             # check state changed
```

### When you must use coordinates (no text, no detectable object)
```bash
# Use find_text as an anchor, then offset
find_text "Color picker" -t app                            # get anchor coordinates
mouse click X,Y -t app --offset 50,30                     # click relative to anchor

# Last resort: crop small area + grid for estimation
screenshot /tmp/crop.png -t app --crop X,Y,W,H --grid 50  # small crop with grid
# Estimate from grid lines (expect ~15-20px error)
```

$ARGUMENTS
