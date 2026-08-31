#!/usr/bin/env bash
set -e

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Setup complete."
echo "1) Start Ollama: ollama serve"
echo "2) Run app:      ./run.sh"
echo "3) Open:         http://127.0.0.1:8000"
