---
description: Send keyboard events to the focused window. Use for UI testing, automation, and interacting with GUI applications.
---

# Send Keys

Send keyboard events to the focused window using `~/bin/sendkeys`.

## Arguments

Parse the user's input after `/sendkeys` to determine what to send:

- Quoted text like `"hello"` → type that text
- Key names like `enter`, `tab`, `escape` → `--key enter`
- Combos like `ctrl+s`, `alt+f4` → `--key ctrl+s`
- Sequences like `tab, tab, enter` → `--keys "tab,tab,enter"`
- `to PATTERN` or `title PATTERN` → `--title PATTERN` (focus target window first)
- `delay N` or `wait N` → `--delay N`
- `repeat N` or `Nx` → `--repeat N` (e.g. `5x tab` = press tab 5 times)
- `pause N` → `--pause N` (milliseconds between repeats)

IMPORTANT: Always use `--title` when targeting a specific app. This focuses the window before sending keys, avoiding alt-tab issues.

## Key reference

Special keys: enter, tab, escape/esc, backspace/bs, delete/del, space, up, down, left, right, home, end, pageup/pgup, pagedown/pgdn, f1-f12, insert, capslock, numlock, scrolllock

Modifiers: ctrl, alt, shift, win (combine with +)

## Procedure

1. Build the sendkeys command from the user's arguments
2. Run it via Bash
3. If the user wants to verify the result, take a screenshot with `~/bin/screenshot`

## Examples

- `/sendkeys enter` → `sendkeys --key enter`
- `/sendkeys ctrl+s` → `sendkeys --key ctrl+s`
- `/sendkeys "Hello World"` → `sendkeys "Hello World"`
- `/sendkeys tab, tab, enter` → `sendkeys --keys "tab,tab,enter"`
- `/sendkeys 5x down` → `sendkeys --repeat 5 --key down`
- `/sendkeys delay 2 ctrl+v` → `sendkeys --delay 2 --key ctrl+v`
- `/sendkeys to notepad "Hello"` → `sendkeys --title notepad "Hello"`
- `/sendkeys to chrome ctrl+t` → `sendkeys --title chrome --key ctrl+t`

## Combining with screenshots

For UI testing, combine with `/screenshot`:
1. Send keys to interact with the UI
2. Take a screenshot to verify the result
3. Repeat as needed

$ARGUMENTS
