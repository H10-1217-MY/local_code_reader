#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Conda の base が有効でも、依存関係はこのプロジェクト専用 .venv に固定する。
python -m venv .venv
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt

echo
echo "Setup complete."
echo "1) Ollama確認: curl http://127.0.0.1:11434/api/tags"
echo "2) Run app:    ./run.sh"
echo "3) Open:       http://127.0.0.1:8000"
