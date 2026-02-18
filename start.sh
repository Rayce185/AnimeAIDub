#!/bin/bash
set -euo pipefail

echo "============================================"
echo "  AnimeAIDub - Universal Media Dubbing Engine"
echo "============================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- Check Python ----
PYTHON=""
for cmd in python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10+ not found. Please install it:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    echo "  macOS: brew install python@3.11"
    exit 1
fi
echo "[OK] Python: $($PYTHON --version)"

# ---- Check FFmpeg ----
if ! command -v ffmpeg &>/dev/null; then
    if [ -f "$SCRIPT_DIR/ffmpeg/ffmpeg" ]; then
        export PATH="$SCRIPT_DIR/ffmpeg:$PATH"
    else
        echo "[ERROR] FFmpeg not found. Please install it:"
        echo "  Ubuntu/Debian: sudo apt install ffmpeg"
        echo "  Fedora: sudo dnf install ffmpeg"
        echo "  macOS: brew install ffmpeg"
        exit 1
    fi
fi
echo "[OK] FFmpeg: Found"

# ---- Create venv if needed ----
if [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[SETUP] Creating virtual environment..."
    $PYTHON -m venv "$SCRIPT_DIR/venv"
fi
echo "[OK] Virtual environment ready"

# ---- Activate venv ----
source "$SCRIPT_DIR/venv/bin/activate"

# ---- Install/update dependencies ----
if [ ! -f "$SCRIPT_DIR/venv/.installed" ]; then
    echo "[SETUP] Installing dependencies (this may take a while on first run)..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r "$SCRIPT_DIR/requirements.txt"
    touch "$SCRIPT_DIR/venv/.installed"
    echo "[OK] Dependencies installed"
else
    echo "[OK] Dependencies already installed"
fi

# ---- Launch app ----
echo ""
echo "============================================"
echo "  Starting AnimeAIDub on http://localhost:29100"
echo "============================================"
echo "  Press Ctrl+C to stop"
echo ""

# Open browser (best effort, non-blocking)
(sleep 2 && xdg-open http://localhost:29100 2>/dev/null || open http://localhost:29100 2>/dev/null || true) &

# Run the app
$PYTHON -m src.main