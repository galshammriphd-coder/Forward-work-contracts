#!/usr/bin/env bash
# Ghalib X Data Collector — launcher for Linux / macOS
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if [ ! -f .venv/.installed ]; then
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium || echo "Chromium download failed; choose an installed browser in Settings."
  touch .venv/.installed
fi
if [ "$1" = "test" ]; then exec .venv/bin/python -m pytest -q tests; fi
exec .venv/bin/python -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1
