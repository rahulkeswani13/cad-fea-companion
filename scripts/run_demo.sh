#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python_bin() {
  if [[ -n "${PYTHON:-}" ]]; then
    echo "$PYTHON"
    return
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "Python 3.11+ not found. Install Python, or set PYTHON=/path/to/python3" >&2
  exit 1
}

if [[ ! -d .venv ]]; then
  PY="$(python_bin)"
  echo "Creating .venv with ${PY}..."
  "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — add GEMINI_API_KEY when ready."
fi

# Ingest docs into local TF-IDF store
.venv/bin/python - <<'PY'
from companion.rag.store import ingest_docs
print(ingest_docs())
PY

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
echo "Starting CAD/FEA Companion at http://${HOST}:${PORT}"
exec .venv/bin/python -m uvicorn companion.main:app --host "$HOST" --port "$PORT"
