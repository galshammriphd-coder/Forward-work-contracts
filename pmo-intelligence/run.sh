#!/usr/bin/env bash
# PMO INTELLIGENCE — local run (macOS / Linux). Needs Python 3.10 or newer.
set -e
cd "$(dirname "$0")/backend"
PY=python3; command -v python3 >/dev/null || PY=python
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo
echo "PMO INTELLIGENCE:  http://localhost:8000"
echo "Sign in:  director@pmo.local  /  Pmo@2026!     (Ctrl+C to stop)"
echo
exec python -m uvicorn app.main:app --port 8000
