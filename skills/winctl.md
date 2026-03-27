---
description: List, focus, minimize, maximize, or close windows. Use to manage Windows GUI windows from the terminal.
---

# Window Control

Manage Windows GUI windows using `~/bin/winctl`.

## Arguments

Parse the user's input after `/winctl`:

- No args or `list` → `winctl list` (list all visible windows)
- `list FILTER` → `winctl list FILTER` (filter by title)
- `focus PATTERN` → `winctl focus PATTERN`
- `minimize PATTERN` → `winctl minimize PATTERN`
- `maximize PATTERN` → `winctl maximize PATTERN`
- `restore PATTERN` → `winctl restore PATTERN`
- `close PATTERN` → `winctl close PATTERN`

PATTERN matches against both window title and process name (case-insensitive substring). Can also be a numeric window handle.

## Procedure

1. Build the winctl command from the user's arguments
2. Run it via Bash
3. Report the result

## Examples

- `/winctl` → `winctl list`
- `/winctl list chrome` → `winctl list chrome`
- `/winctl focus notepad` → `winctl focus notepad`
- `/winctl minimize eclipse` → `winctl minimize eclipse`
- `/winctl close "Untitled"` → `winctl close "Untitled"`

$ARGUMENTS
