# WSL UI Automation Toolkit

A comprehensive GUI automation toolkit for Windows applications from WSL2. Combines low-level input tools (screenshot, mouse, keyboard) with AI-powered vision (OCR via EasyOCR, object detection via YOLO) for intelligent UI interaction.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  High-level tools                                       │
│                                                         │
│  Text interaction          Object detection             │
│  click_text · find_text    detect (YOLO-World + COCO)   │
│  wait_for · read_screen                                 │
│         │                          │                    │
│   ┌─────┴─────┐             ┌──────┴──────┐             │
│   │ OCR Server │             │ YOLO Server │             │
│   │ :18200     │             │ :18201      │             │
│   │ EasyOCR    │             │ ~15ms/image │             │
│   │ ~1.5s/scan │             └─────────────┘             │
│   └───────────┘                                         │
├─────────────────────────────────────────────────────────┤
│  Low-level tools (direct Windows API via PowerShell)    │
│  screenshot · mouse · sendkeys · winctl                 │
└─────────────────────────────────────────────────────────┘
```

## Setup

### Prerequisites
- WSL2 with GPU passthrough (NVIDIA)
- Python 3.10+
- PowerShell (Windows side, called from WSL)

### Installation

```bash
# Copy tools to ~/bin/ (must be in PATH)
cp screenshot mouse sendkeys winctl find_text click_text wait_for read_screen detect ~/bin/
cp ocr_server.py yolo_server.py ~/bin/

# Install Python dependencies
pip install ultralytics easyocr torch torchvision opencv-python

# YOLO models auto-download on first use: yolov8s.pt (21MB), yolov8s-world.pt (26MB)

# Copy Claude Code skills (optional, for /ui slash command)
cp skills/*.md ~/.claude/commands/
```

### Start GPU servers

```bash
find_text --start         # OCR server on :18200 (~5s to load, then ~1.5s/scan)
detect --start            # YOLO server on :18201 (~3s to load, then ~15ms/detect)
```

## Tools

### Low-level: Direct Windows API

| Tool | Purpose | Example |
|------|---------|---------|
| `screenshot` | Capture screen/window | `screenshot /tmp/s.png -t chrome` |
| `mouse` | Click, drag, scroll | `mouse click 500,300 -t chrome` |
| `sendkeys` | Type text, press keys | `sendkeys -t app "hello"` |
| `winctl` | Manage windows | `winctl focus chrome` |

All support `--title`/`-t` for targeting specific windows by title/process name.

### High-level: OCR-powered (text interaction)

| Tool | Purpose | Example |
|------|---------|---------|
| `click_text` | Find text + click | `click_text "Submit" -t chrome` |
| `find_text` | Find text position | `find_text "Search" -t chrome` |
| `wait_for` | Wait for text to appear/disappear | `wait_for "Done" -t chrome` |
| `read_screen` | OCR all text on screen | `read_screen -t chrome --text-only` |

### High-level: YOLO-powered (object detection)

| Tool | Purpose | Example |
|------|---------|---------|
| `detect` | Find objects by class name | `detect -t chrome "chair,car"` |
| `detect --coco` | Detect 80 COCO classes | `detect -t chrome --coco` |

**YOLO-World** accepts any text description (open vocabulary, no training needed).
**YOLO COCO** is faster and more reliable for its 80 fixed classes (person, car, chair, etc.).

## Usage patterns

### Click a button by its label
```bash
click_text "Submit" -t chrome
```

### Fill a form
```bash
click_text "Username" -t chrome --offset 200,0    # click input right of label
sendkeys -t chrome "myuser"
sendkeys -t chrome --key tab
sendkeys -t chrome "mypassword"
click_text "Sign In" -t chrome
```

### Wait for page load
```bash
sendkeys -t chrome --key ctrl+l
sendkeys -t chrome "https://example.com"
sendkeys -t chrome --key enter
wait_for "Welcome" -t chrome --timeout 10
```

### Read page content
```bash
read_screen -t chrome --text-only          # text grouped by lines
read_screen -t chrome --json               # full JSON with positions
read_screen -t chrome -r 0,0,500,200       # OCR specific region only
```

### Detect objects
```bash
detect -t chrome                          # detect COCO objects (80 classes)
detect -t chrome "chair,car,person"       # detect specific objects (YOLO-World)
detect -t chrome "button,icon,link"       # open-vocabulary detection
detect --file image.png "chair" -c 0.3    # detect in file, confidence 0.3
detect -t chrome --coco -j                # COCO detection, JSON output
detect --list                             # list all 80 COCO class names
detect --start / --stop / --status        # manage YOLO server
```

### Navigate browser
```bash
sendkeys -t chrome --key ctrl+l            # focus address bar
sendkeys -t chrome "https://example.com"
sendkeys -t chrome --key enter
```

## When to use what

| Task | Best tool | Speed |
|------|-----------|-------|
| Click a button/link with visible text | `click_text` | ~2s |
| Detect real-world objects (chair, car) | `detect` | ~15ms |
| Detect arbitrary objects by description | `detect "description"` | ~15ms |
| Click a specific pixel coordinate | `mouse click` | instant |
| Type text into focused field | `sendkeys` | instant |
| Wait for async operation | `wait_for` | ~2s/poll |
| Read all text on page | `read_screen` | ~1.5s |
| Find position of text without clicking | `find_text` | ~1.5s |
| Take a screenshot to look at | `screenshot` | ~0.3s |

### Decision tree
- **"Click the Submit button"** → `click_text` (text-based)
- **"Find all chairs in this image"** → `detect "chair"` (object detection)
- **"What's on screen?"** → `read_screen` (text) or `detect --coco` (objects)

## Performance

With GPU servers running (RTX 4080):

| Operation | Time | Server port |
|-----------|------|-------------|
| Screenshot capture | ~0.3s | — |
| **YOLO detection** | **~15ms** | :18201 |
| OCR scan (1294x1399) | ~1.5s | :18200 |
| `click_text` end-to-end | ~2s | :18200 |
| `wait_for` per poll | ~2s | :18200 |

Without servers (cold start), add ~3-5s for model loading.

## Claude Code integration

The `skills/` directory contains Claude Code slash commands:
- `/ui` — unified reference for all tools
- `/screenshot` — capture and view screenshots
- `/mouse` — mouse control
- `/sendkeys` — keyboard input
- `/winctl` — window management

Copy to `~/.claude/commands/` to enable.

## Design decisions

- **OCR for text, YOLO for objects**: OCR finds text labels (buttons, links). YOLO detects and classifies visual objects in 15ms. Each excels at a different task — combining them covers both text-based UI and visual content.
- **YOLO-World for open vocabulary**: Detects arbitrary objects by text description without training — "find all chairs" just works. COCO model is faster for its 80 fixed classes.
- **Persistent GPU servers**: Model loading takes 3-5s. Two servers (OCR :18200, YOLO :18201) stay warm and respond in milliseconds to seconds.
- **Window-relative coordinates**: `--title` flag on all tools makes coordinates independent of window position. PrintWindow API captures even occluded windows.
- **EasyOCR over Tesseract**: Better out-of-the-box accuracy for mixed languages (Polish + English), GPU-accelerated, no system package dependency.
