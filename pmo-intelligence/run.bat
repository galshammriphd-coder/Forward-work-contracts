@echo off
rem PMO INTELLIGENCE - local run (Windows). Needs Python 3.10 or newer from python.org.
cd /d "%~dp0backend"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
if errorlevel 1 (
  echo Installation failed. Check your internet connection and Python version.
  pause
  exit /b 1
)
echo.
echo PMO INTELLIGENCE:  http://localhost:8000
echo Sign in:  director@pmo.local  /  Pmo@2026!     (Ctrl+C to stop)
echo.
start "" http://localhost:8000
python -m uvicorn app.main:app --port 8000
pause
