#!/bin/bash
# Install WSL UI Automation Toolkit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${1:-$HOME/bin}"

echo "Installing scripts to $BIN_DIR..."
mkdir -p "$BIN_DIR"
cp "$SCRIPT_DIR/bin/"* "$BIN_DIR/"
chmod +x "$BIN_DIR/"*

# Check if BIN_DIR is on PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "WARNING: $BIN_DIR is not on your PATH."
  echo "Add this to your shell profile (~/.bashrc or ~/.zshrc):"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo ""
echo "Installed tools:"
echo "  Low-level:  screenshot, mouse, sendkeys, winctl"
echo "  OCR:        find_text, click_text, wait_for, read_screen"
echo "  YOLO:       detect"
echo "  Image:      imgcrop"
echo "  Servers:    ocr_server.py, yolo_server.py"

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
python3 -c "import ultralytics, easyocr, torch, cv2" 2>/dev/null && echo "  All dependencies found." || {
  echo "  Missing dependencies. Install with:"
  echo "    pip install ultralytics easyocr torch torchvision opencv-python"
}

# Optionally install Claude Code skills
if [ -d "$HOME/.claude" ]; then
  read -p "Install Claude Code skills (slash commands)? [y/N] " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.claude/commands"
    cp "$SCRIPT_DIR/skills/"*.md "$HOME/.claude/commands/"
    echo "Installed skills: /screenshot, /sendkeys, /mouse, /winctl, /ui"
  fi
fi

echo ""
echo "Done! Start GPU servers with:"
echo "  find_text --start    # OCR server :18200"
echo "  detect --start       # YOLO server :18201"
