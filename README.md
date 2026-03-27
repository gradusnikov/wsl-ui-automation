# WSL UI Automation Toolkit

Give Claude Code (or any AI coding agent) **eyes and hands** on your Windows desktop from WSL.

Four bash scripts that use PowerShell and Win32 APIs to capture screens, control the mouse, send keyboard input, and manage windows — all from the WSL command line. Includes Claude Code skills (slash commands) for seamless AI-driven UI automation.

## What can it do?

- **See** the screen or any window (even behind other windows)
- **Click** buttons, links, and UI elements by coordinates
- **Type** text into any application
- **Manage** windows — list, focus, minimize, maximize, close
- **Automate** UI testing with a vision-action loop

## Demo

Built and tested live — Claude Code autonomously:
1. Navigated Chrome to Google, searched for a topic, and clicked the first result
2. Explored a desktop application, discovered its UI structure, and navigated through it
3. Typed text into Notepad with special characters (`a+b=c (100%) ~hello^ {world}`)

All without manual window switching or focus management.

## Installation

### Scripts

Copy the scripts to a directory on your `$PATH`:

```bash
cp bin/* ~/bin/
chmod +x ~/bin/screenshot ~/bin/sendkeys ~/bin/mouse ~/bin/winctl
```

### Claude Code Skills (optional)

Copy the skill files to make them available as slash commands in Claude Code:

```bash
# Global (all projects)
cp skills/*.md ~/.claude/commands/

# Or per-project
cp skills/*.md .claude/commands/
```

### Permissions (recommended)

Add to your `.claude/settings.local.json` to avoid permission prompts:

```json
{
  "permissions": {
    "allow": [
      "Bash(~/bin/screenshot:*)",
      "Bash(~/bin/sendkeys:*)",
      "Bash(~/bin/winctl:*)",
      "Bash(~/bin/mouse:*)",
      "Bash(sleep:*)",
      "Bash(powershell.exe:*)"
    ]
  }
}
```

## Tools

### screenshot

Capture the screen, a specific window, or a region.

```bash
screenshot                                # primary screen -> /tmp/screenshot.png
screenshot shot.png                       # custom filename
screenshot -t chrome                      # capture Chrome (works even if behind other windows)
screenshot -w                             # capture the focused window
screenshot -s 1                           # capture second monitor
screenshot -a                             # all monitors stitched together
screenshot -c                             # save clipboard image to file
screenshot -r 100,200,800,600             # capture region (X,Y,W,H)
screenshot --crop 0,0,500,400             # crop after capture
screenshot --scale 50                     # downscale by 50%
screenshot -d 3 -w                        # delay 3 seconds, then capture
screenshot -t notepad --crop 0,0,800,600  # capture and crop Notepad
screenshot --list                         # list available screens
screenshot --hide -t chrome               # hide terminal, capture Chrome
screenshot -o shot.png                    # open image after saving

# Annotations — draw on screenshots
screenshot -t chrome --arrow 200,350,400,200              # arrow from → to
screenshot -t chrome --circle 500,300,40                   # circle at (x,y) radius r
screenshot -t chrome --highlight 200,100,400,80            # semi-transparent highlight
screenshot -t chrome --label 210,90 "Click here"           # text with dark outline
screenshot -t chrome --color yellow --arrow 100,100,200,50 # change color
# Colors: red (default), green, blue, yellow, cyan, white
# Multiple annotations can be combined and are drawn in order
screenshot -t app --highlight 50,50,300,100 --arrow 20,100,50,80 --label 20,115 "Here"
```

**Key feature**: `--title` uses the `PrintWindow` API, which captures a window's content even when it's behind other windows. No need to focus or bring it to front.

**Annotations**: Draw arrows, circles, highlights, and labels directly on screenshots. Useful for AI agents to visually communicate what they're seeing or pointing at.

### mouse

Move, click, drag, and scroll.

```bash
mouse pos                           # print current cursor position (X,Y)
mouse move 500,300                  # move cursor to position
mouse click 500,300                 # left click at position
mouse click                         # left click at current position
mouse rclick 500,300                # right click
mouse mclick 500,300                # middle click
mouse dclick 200,100                # double click
mouse drag 100,200 500,300          # drag from (100,200) to (500,300)
mouse scroll down 5                 # scroll down 5 notches
mouse scroll up                     # scroll up 3 notches (default)
mouse scroll left 3                 # horizontal scroll
mouse hold 100,200                  # press and hold left button
mouse release 500,300               # release at position
mouse click 50,80 -t notepad        # click relative to Notepad's top-left
mouse -d 2 click 500,300            # wait 2 seconds, then click
```

**Key feature**: `--title` makes coordinates relative to the target window's top-left corner, so positions from screenshots map directly to click coordinates.

### sendkeys

Send keyboard events to any window.

```bash
sendkeys "Hello World"                    # type text (uses clipboard paste)
sendkeys --key enter                      # press Enter
sendkeys --key ctrl+s                     # key combination
sendkeys --key ctrl+shift+s              # multi-modifier combo
sendkeys --key alt+f4                     # close window
sendkeys --keys "tab,tab,enter"           # key sequence
sendkeys -r 5 --key tab                   # press Tab 5 times
sendkeys -r 3 -p 500 --key down           # Down 3x, 500ms apart
sendkeys -d 2 --key enter                 # delay 2 seconds, then press Enter
sendkeys -t notepad "Hello World"         # focus Notepad, then type
sendkeys -t chrome --key ctrl+l           # focus Chrome address bar
sendkeys --key win+d                      # show desktop (Win key combos)
```

**Key feature**: Text input uses clipboard paste (Ctrl+V), which correctly handles all special characters (`+`, `^`, `%`, `~`, `()`, `{}`, etc.) without SendKeys escaping issues. The original clipboard is saved and restored.

**Supported keys**: enter, tab, escape/esc, backspace/bs, delete/del, space, up, down, left, right, home, end, pageup/pgup, pagedown/pgdn, f1-f12, insert/ins, capslock, numlock, scrolllock

**Modifiers**: ctrl, alt, shift, win (combine with `+`)

### winctl

List and manage Windows GUI windows.

```bash
winctl list                         # list all visible windows
winctl list chrome                  # filter by title or process name
winctl focus notepad                # bring Notepad to foreground
winctl focus 12345                  # focus by window handle
winctl minimize eclipse             # minimize a window
winctl maximize chrome              # maximize
winctl restore notepad              # restore minimized window
winctl close "Untitled"             # close window (sends WM_CLOSE)
```

Output includes window handle, PID, process name, and title. The active window is marked with `*`.

## Claude Code Skills

The skills turn these tools into slash commands with natural language parsing:

| Skill | Command | Description |
|---|---|---|
| `/screenshot` | `/screenshot chrome` | Capture and analyze a window |
| `/mouse` | `/mouse click 200,50 to notepad` | Mouse control with targeting |
| `/sendkeys` | `/sendkeys to chrome ctrl+t` | Keyboard input to any window |
| `/winctl` | `/winctl list` | Window management |
| `/ui` | `/ui look at chrome` | Unified reference — interprets intent |

The `/ui` skill is a meta-skill that documents the full workflow and helps the AI choose the right tool.

## Vision-Action Loop Pattern

The core pattern for AI-driven UI automation:

```bash
# 1. See — capture the target window
screenshot /tmp/s.png -t myapp

# 2. Get dimensions (screenshot pixels = window coordinates)
powershell.exe -Command "
  Add-Type -AssemblyName System.Drawing
  \$i = [System.Drawing.Image]::FromFile('$(wslpath -w /tmp/s.png)')
  Write-Host \"\$(\$i.Width)x\$(\$i.Height)\""

# 3. Act — click, type, scroll based on what you see
mouse click 200,350 -t myapp
sendkeys -t myapp "search query"
sendkeys -t myapp --key enter

# 4. Verify — screenshot again
screenshot /tmp/s.png -t myapp
```

### Browser Automation Example

```bash
# Navigate to a URL
sendkeys -t chrome --key ctrl+l           # focus address bar
sendkeys -t chrome "https://example.com"  # type URL
sendkeys -t chrome --key enter            # go
sleep 2                                    # wait for page load

# Interact with the page
screenshot /tmp/s.png -t chrome            # see the page
mouse click 300,400 -t chrome              # click an element
sendkeys -t chrome "form input"            # type into a field
screenshot /tmp/s.png -t chrome            # verify
```

## Requirements

- **WSL** (Windows Subsystem for Linux) — WSL2 recommended
- **PowerShell** — available via `powershell.exe` from WSL (ships with Windows)
- **Bash** — any modern bash (zsh compatible)

No additional dependencies. The scripts use PowerShell's `Add-Type` to call Win32 APIs directly.

## How It Works

| Feature | API |
|---|---|
| Window capture (behind other windows) | `PrintWindow` via user32.dll |
| Screen capture | `Graphics.CopyFromScreen` (.NET) |
| Window enumeration & management | `EnumWindows`, `SetForegroundWindow`, `ShowWindow` |
| Mouse control | `SetCursorPos`, `mouse_event` |
| Keyboard (special keys) | `SendKeys.SendWait` (.NET) |
| Keyboard (text) | Clipboard + `SendKeys('^v')` |
| Window-relative coordinates | `GetWindowRect` offset calculation |

## Limitations

- **Text input via clipboard**: `sendkeys` temporarily uses the clipboard for text. The original content is saved and restored, but rapid concurrent clipboard use could conflict.
- **Window matching**: `--title` matches by case-insensitive substring against both window title and process name. If multiple windows match, the first found is used.
- **DPI scaling**: Coordinates are in physical screen pixels. On high-DPI displays with scaling, PrintWindow captures at full resolution — screenshot dimensions match mouse coordinates directly.
- **Focus for keyboard**: `sendkeys --title` must bring the window to the foreground to send keys. `screenshot --title` does NOT need focus (uses PrintWindow).

## License

MIT
