#!/usr/bin/env bash
# Start RemakeFace2API. Safe on a fresh git clone: creates runtime dirs + .venv automatically.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8610}"
PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "[error] Python 3.10+ is required." >&2
  exit 1
fi

mkdir -p state server/data/generated examples

if [ ! -x .venv/bin/python ]; then
  echo "[init] creating .venv..."
  "$PYTHON" -m venv .venv || {
    echo "[error] python venv unavailable. Debian/Ubuntu: sudo apt install -y python3-venv" >&2
    exit 1
  }
fi

.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

echo "[run] http://0.0.0.0:${PORT}  (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port "$PORT"
