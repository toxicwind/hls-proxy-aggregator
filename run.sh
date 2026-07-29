#!/usr/bin/env bash
# JMP2-Uber-Max Launcher
# Usage: ./run.sh [--port 9223] [--source /path/to/m3us]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create venv if missing
if [[ ! -d .venv ]]; then
    echo "[JMP2] Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install deps
if [[ ! -f .venv/.installed ]] || [[ requirements.txt -nt .venv/.installed ]]; then
    echo "[JMP2] Installing dependencies..."
    pip install -q -r requirements.txt
    touch .venv/.installed
fi

# Default args
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9223}"
SOURCE="${SOURCE:-source/Dji-you-main}"

# Ensure source exists
if [[ ! -d "$SOURCE" ]]; then
    echo "[JMP2] ERROR: Source directory not found: $SOURCE"
    echo "[JMP2] Place M3U files in $SOURCE or set SOURCE env var"
    exit 1
fi

echo "[JMP2] 🐸 Starting JMP2-Uber-Max on $HOST:$PORT"
echo "[JMP2] Source: $SOURCE"
python3 -m src.main --config config.yaml --source "$SOURCE" --host "$HOST" --port "$PORT" "$@"
