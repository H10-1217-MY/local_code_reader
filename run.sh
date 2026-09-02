#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Error: .venv が見つかりません。先に ./setup.sh を実行してください。" >&2
  exit 1
fi

exec "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
