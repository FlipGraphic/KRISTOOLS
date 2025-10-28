#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Create a Python venv if missing
if [ ! -d "$ROOT_DIR/.venv" ]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi
source "$ROOT_DIR/.venv/bin/activate"

# Install deps
python -m pip install --upgrade pip
pip install -r "$ROOT_DIR/requirements.txt"

# Start Amazon PA-API tool (5050) in background
PYTHONUNBUFFERED=1 python "$ROOT_DIR/amz_api_tool.py" &
AMZ_PID=$!

# Start local dashboard/server (8000)
PYTHONUNBUFFERED=1 python "$ROOT_DIR/server.py" &
WEB_PID=$!

echo "Servers started: amz_api_tool.py PID=$AMZ_PID, server.py PID=$WEB_PID"
echo "- Amazon:  http://127.0.0.1:5050/health"
echo "- Dashboard:http://127.0.0.1:8000/Daily.html"

echo "Press Ctrl+C to stop both."
trap 'echo Stopping...; kill $AMZ_PID $WEB_PID 2>/dev/null || true; wait $AMZ_PID $WEB_PID 2>/dev/null || true; exit 0' INT TERM
wait $AMZ_PID $WEB_PID
