---
description: Capture a screenshot and analyze it. Use when you need to see what's on the user's screen.
---

# Screenshot

Capture a screenshot using the `screenshot` tool at `~/bin/screenshot` and read the result.

## Arguments

The user may provide arguments after `/screenshot`. Parse them to determine the mode:

- No args or `screen` → capture the primary screen
- `window` or `win` or `w` → capture the active window (`--window`)
- `all` → capture all monitors (`--all`)
- `clipboard` or `clip` or `c` → save clipboard image (`--clipboard`)
- A number like `0`, `1`, `2` → capture that screen index (`--screen N`)
- `list` → list available screens (`--list`), do NOT capture
- `title PATTERN` or a window/process name → capture that window (`--title PATTERN`) — works even if window is behind others
- `hide` can be combined with any mode to hide the terminal first

Additional modifiers the user may specify:
- `delay N` or `wait N` → add `--delay N`
- `scale N` → add `--scale N`
- `region X,Y,W,H` → add `--region X,Y,W,H`

Annotations (use to highlight things for the user):
- `arrow X1,Y1,X2,Y2` → add `--arrow X1,Y1,X2,Y2`
- `circle X,Y,R` → add `--circle X,Y,R`
- `highlight X,Y,W,H` → add `--highlight X,Y,W,H`
- `label X,Y "text"` → add `--label X,Y "text"`
- `color NAME` → add `--color NAME` (red,green,blue,yellow,cyan,white — applies to subsequent annotations)

IMPORTANT: Use annotations proactively when showing screenshots to the user. Draw arrows, circles, or highlights to point out what you're describing — it's much clearer than text alone.

IMPORTANT: Prefer `--title` over `--window` when targeting a specific app. `--title` uses PrintWindow API to capture the window even when obscured. `--window` only captures the foreground window.

## Procedure

1. Build the command based on the user's arguments. Default output file: `/tmp/screenshot.png`
2. Run the screenshot command via Bash
3. Read the resulting image file with the Read tool
4. Describe what you see, or use it for whatever task the user needs

## Examples

- `/screenshot` → `screenshot /tmp/screenshot.png`
- `/screenshot window` → `screenshot /tmp/screenshot.png --window`
- `/screenshot window hide` → `screenshot /tmp/screenshot.png --window --hide`
- `/screenshot 1` → `screenshot /tmp/screenshot.png --screen 1`
- `/screenshot all scale 50` → `screenshot /tmp/screenshot.png --all --scale 50`
- `/screenshot delay 3 window` → `screenshot /tmp/screenshot.png --window --delay 3`
- `/screenshot list` → `screenshot --list`
- `/screenshot clipboard` → `screenshot /tmp/screenshot.png --clipboard`
- `/screenshot notepad` → `screenshot /tmp/screenshot.png --title notepad`
- `/screenshot chrome scale 50` → `screenshot /tmp/screenshot.png --title chrome --scale 50`
- `/screenshot chrome arrow 200,350,400,200 label 400,190 "Click here"` → `screenshot /tmp/screenshot.png -t chrome --arrow 200,350,400,200 --label 400,190 "Click here"`
- `/screenshot notepad highlight 50,50,300,100 color yellow circle 200,200,30` → `screenshot /tmp/screenshot.png -t notepad --highlight 50,50,300,100 --color yellow --circle 200,200,30`

$ARGUMENTS
