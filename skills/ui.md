---
description: UI automation — interact with Windows GUI apps using screenshot, mouse, sendkeys, and winctl. Use for UI testing, browser automation, clicking buttons, filling forms, or any visual interaction.
---

# UI Automation

You have a full Windows GUI automation toolkit at `~/bin/`. Use it to see, click, type, and manage windows.

## Tools

| Tool | Command | Purpose |
|---|---|---|
| **screenshot** | `~/bin/screenshot` | Capture screen or specific window |
| **mouse** | `~/bin/mouse` | Move, click, drag, scroll |
| **sendkeys** | `~/bin/sendkeys` | Send keyboard input (keys and text) |
| **winctl** | `~/bin/winctl` | List, focus, minimize, maximize, close windows |

## Core workflow: vision-action loop

1. **See** — `screenshot -t <app>` to capture a window (works even if behind other windows)
2. **Act** — `mouse click X,Y -t <app>` or `sendkeys -t <app> "text"` to interact
3. **Verify** — `screenshot -t <app>` again to confirm the result
4. Repeat as needed

## Quick reference

### Screenshot (`~/bin/screenshot`)
```
screenshot                            # primary screen → /tmp/screenshot.png
screenshot -t chrome                  # capture Chrome window (PrintWindow, works even if occluded)
screenshot -w                         # capture focused/foreground window
screenshot -s 1                       # capture second monitor
screenshot -a                         # all monitors stitched
screenshot -c                         # save clipboard image
screenshot -r 100,200,800,600         # capture region (X,Y,W,H)
screenshot --scale 50                 # downscale 50%
screenshot -d 3 -w                    # delay 3s, capture focused window
screenshot --list                     # list available screens

# Annotations — draw on screenshots to communicate visually
screenshot -t app --arrow 100,200,300,150         # arrow from → to
screenshot -t app --circle 500,300,40             # circle at (x,y) radius r
screenshot -t app --highlight 200,100,400,80      # semi-transparent highlight box
screenshot -t app --label 210,90 "Click here"     # text label with dark outline
screenshot -t app --color yellow --arrow 0,0,50,50 # change color (red,green,blue,yellow,cyan,white)
# Multiple annotations stack: --highlight ... --arrow ... --label ...
```

IMPORTANT: Use annotations proactively when showing screenshots to the user. An arrow pointing at the relevant element is worth a paragraph of description.

### Mouse (`~/bin/mouse`)
```
mouse pos                             # get current cursor position
mouse move 500,300                    # move cursor
mouse click 500,300                   # left click at position
mouse click 50,80 -t notepad          # click relative to Notepad window
mouse rclick 500,300                  # right click
mouse dclick 200,100                  # double click
mouse drag 100,200 500,300            # drag from → to
mouse scroll down 5                   # scroll down 5 notches
mouse scroll up                       # scroll up (default 3)
mouse -d 2 click 500,300              # delay 2s then click
```

### Sendkeys (`~/bin/sendkeys`)
```
sendkeys -t notepad "Hello World"     # type text into Notepad (uses clipboard paste)
sendkeys -t chrome --key ctrl+l       # focus Chrome address bar
sendkeys --key enter                  # press Enter in focused window
sendkeys --key ctrl+shift+s           # key combo
sendkeys --keys "tab,tab,enter"       # key sequence
sendkeys -r 5 --key tab               # press Tab 5 times
sendkeys -r 3 -p 500 --key down       # Down 3x, 500ms apart
sendkeys -d 2 --key enter             # delay 2s, press Enter
```

### Winctl (`~/bin/winctl`)
```
winctl list                           # list all visible windows (handle, PID, process, title)
winctl list chrome                    # filter by title/process
winctl focus notepad                  # bring window to foreground
winctl minimize eclipse               # minimize
winctl maximize chrome                # maximize
winctl restore notepad                # restore minimized window
winctl close "Untitled"               # close window (sends WM_CLOSE)
```

## Key patterns

### Targeting windows
All tools support `--title`/`-t` to target a specific window by title or process name (case-insensitive substring match):
- `screenshot -t chrome` — captures Chrome even if behind other windows (uses PrintWindow API)
- `mouse click 100,200 -t chrome` — coordinates relative to Chrome's top-left corner
- `sendkeys -t notepad "text"` — focuses Notepad then types

**Always prefer `--title` over alt-tab.** It's reliable and doesn't depend on window focus.

### Coordinate mapping
When using `mouse` with `--title`, coordinates are relative to the target window. To find coordinates:
1. Take a screenshot: `screenshot /tmp/s.png -t app`
2. Check actual pixel dimensions: `powershell.exe -Command "Add-Type -AssemblyName System.Drawing; \$i = [System.Drawing.Image]::FromFile('$(wslpath -w /tmp/s.png)'); Write-Host \"\$(\$i.Width)x\$(\$i.Height)\""`
3. The screenshot pixel dimensions match the window's pixel dimensions — use them directly for mouse coordinates

### Text input
`sendkeys` uses clipboard paste (Ctrl+V) for text, which handles all special characters correctly (`+`, `%`, `^`, `~`, `()`, `{}`, etc.). The original clipboard is saved and restored.

### Browser automation pattern
```bash
# Navigate to a URL
sendkeys -t chrome --key ctrl+l        # focus address bar
sendkeys -t chrome "https://example.com"
sendkeys -t chrome --key enter
sleep 2                                 # wait for page load
screenshot /tmp/s.png -t chrome         # see the result

# Click on a page element
mouse click X,Y -t chrome              # coordinates from screenshot

# Fill a form field
mouse click X,Y -t chrome              # click the field
sendkeys -t chrome "form value"         # type into it
```

## Interpreting the user's request

When the user says `/ui`, parse their intent:

- **"look at X"** or **"what's on screen"** → screenshot
- **"click on X"** → screenshot to find it, then mouse click
- **"type X into Y"** → sendkeys with --title
- **"scroll down in X"** → mouse scroll with --title
- **"open X"** → winctl focus or sendkeys to launch
- **"test X"** → vision-action loop: screenshot → interact → verify
- **"list windows"** → winctl list

For complex multi-step interactions, chain the tools and verify after each action with a screenshot.

$ARGUMENTS
