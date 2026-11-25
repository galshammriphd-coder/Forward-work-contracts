#!/usr/bin/env bash
# AI-Powered PMO Platform — local run (macOS / Linux). Needs Python 3.10 or newer.
set -e
cd "$(dirname "$0")/backend"
PY=python3; command -v python3 >/dev/null || PY=python
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
echo 'Installing packages (first run downloads about 60 MB)...'
pip install --disable-pip-version-check -r requirements-local.txt
echo
echo "AI-Powered PMO Platform:  http://localhost:8000"
echo "Sign in:  director@pmo.local  /  Pmo@2026!     (Ctrl+C to stop)"
echo
exec python -m uvicorn app.main:app --port 8000
