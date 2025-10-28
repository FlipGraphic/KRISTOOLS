#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Kill any existing processes
echo "[RUN] Checking for existing processes..."
pkill -f "python mention_bot.py" 2>/dev/null && echo "[RUN] Killed old mention_bot.py" || true
pkill -f "python message_forwarder.py" 2>/dev/null && echo "[RUN] Killed old message_forwarder.py" || true
pkill -f "python d2d.py" 2>/dev/null && echo "[RUN] Killed old d2d.py" || true
pkill -f "python http_server.py" 2>/dev/null && echo "[RUN] Killed old HTTP server" || true
pkill -f "python -m http.server 8080" 2>/dev/null && echo "[RUN] Killed old simple HTTP server" || true
sleep 1

# Ensure venv if present is activated
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

export PYTHONUNBUFFERED=1

# Prefer tokenkeys.env if exists
if [[ -f tokenkeys.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source tokenkeys.env
  set +a
elif [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Launch mention bot and filter bot in background, then bridge in foreground
python mention_bot.py &
MENTION_PID=$!

echo "[RUN] Started mention_bot.py (PID ${MENTION_PID})"

python message_forwarder.py &
FORWARDER_PID=$!

echo "[RUN] Started message_forwarder.py (PID ${FORWARDER_PID})"

echo "[RUN] Launching d2d.py (foreground)..."
python d2d.py
EXIT_CODE=$?

echo "[STOP] d2d.py exited with code ${EXIT_CODE}. Stopping background bots..."
kill ${MENTION_PID} ${FORWARDER_PID} 2>/dev/null || true
wait ${MENTION_PID} ${FORWARDER_PID} 2>/dev/null || true

exit ${EXIT_CODE}
