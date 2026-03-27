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

$ARGUMENTS
