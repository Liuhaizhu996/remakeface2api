#!/usr/bin/env bash
# Start RemakeFace WebUI backend (default port 8610)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8610}"
if [ ! -x .venv/bin/python ]; then
  echo "[init] creating venv..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
echo "[run] http://0.0.0.0:${PORT}  (ctrl-c to stop)"
exec .venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT}"
