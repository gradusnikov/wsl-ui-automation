---
description: Control the mouse — move, click, drag, scroll. Use for GUI interaction, clicking buttons, selecting items, and UI testing.
---

# Mouse Control

Control the mouse using `~/bin/mouse`.

## Arguments

Parse the user's input after `/mouse`:

- `pos` → `mouse pos` (get current position)
- `move X,Y` → `mouse move X,Y`
- `click X,Y` → `mouse click X,Y` (left click)
- `click` → `mouse click` (click at current position)
- `rclick X,Y` → `mouse rclick X,Y` (right click)
- `dclick X,Y` → `mouse dclick X,Y` (double click)
- `drag X1,Y1 X2,Y2` → `mouse drag X1,Y1 X2,Y2`
- `scroll up/down [N]` → `mouse scroll down 5`
- `to PATTERN` or `title PATTERN` → add `--title PATTERN` (coordinates relative to window)
- `delay N` or `wait N` → add `--delay N`

IMPORTANT: When using `--title`, coordinates are relative to the window's top-left corner, not absolute screen position. This is crucial for clicking on UI elements seen in screenshots.

## Workflow: vision-action loop

For clicking on elements visible in a screenshot:
1. Take a screenshot with `/screenshot -t appname`
2. Identify the element's approximate position within the window
3. Use `mouse click X,Y -t appname` with coordinates relative to the window
4. Screenshot again to verify

## Examples

- `/mouse pos` → `mouse pos`
- `/mouse click 500,300` → `mouse click 500,300`
- `/mouse click 200,50 to notepad` → `mouse click 200,50 -t notepad`
- `/mouse dclick 100,100 to chrome` → `mouse dclick 100,100 -t chrome`
- `/mouse scroll down 5` → `mouse scroll down 5`
- `/mouse drag 100,200 500,300` → `mouse drag 100,200 500,300`

$ARGUMENTS
