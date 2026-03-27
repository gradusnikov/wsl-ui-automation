#!/bin/bash
# Install WSL UI Automation Toolkit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${1:-$HOME/bin}"

echo "Installing scripts to $BIN_DIR..."
mkdir -p "$BIN_DIR"
cp "$SCRIPT_DIR/bin/"* "$BIN_DIR/"
chmod +x "$BIN_DIR/screenshot" "$BIN_DIR/sendkeys" "$BIN_DIR/mouse" "$BIN_DIR/winctl"

# Check if BIN_DIR is on PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "WARNING: $BIN_DIR is not on your PATH."
  echo "Add this to your shell profile (~/.bashrc or ~/.zshrc):"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo ""
echo "Installed: screenshot, sendkeys, mouse, winctl"

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
echo "Done! Try: winctl list"
