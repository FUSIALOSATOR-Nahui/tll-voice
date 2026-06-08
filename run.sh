#!/usr/bin/env bash
# TLL-Voice launcher for Linux (Kali / Debian-based)
# Requires X11 session (not Wayland)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- System deps (run once) ---
# sudo apt install -y python3-pip python3-venv portaudio19-dev xclip

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install/update deps
pip install -q -r requirements.txt

# Load .env if present
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "[launch] Starting TLL-Voice..."
python3 main.py
