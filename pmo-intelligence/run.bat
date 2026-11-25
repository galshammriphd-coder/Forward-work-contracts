@echo off
setlocal
title PMO INTELLIGENCE
cd /d "%~dp0backend"

echo ============================================================
echo  PMO INTELLIGENCE - local run
echo ============================================================
echo.
echo [1/4] Looking for Python...
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo  Python was not found.
  echo  Install Python 3.10 or newer from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" in the installer, then run this file again.
  echo.
  pause
  exit /b 1
)
%PY% --version
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo.
  echo  This Python is older than 3.10. Install a newer one from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo.
echo [2/4] Preparing the isolated environment (first run only)...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  Could not create the environment. See the message above.
    pause
    exit /b 1
  )
)

echo.
echo [3/4] Installing packages. The first run downloads about 60 MB; progress is shown below.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-local.txt
if errorlevel 1 (
  echo.
  echo  Installation failed. The lines above say why ^(usually no internet, a proxy, or a very new Python^).
  pause
  exit /b 1
)

echo.
echo [4/4] Starting the server...
echo.
echo    Open:     http://localhost:8000
echo    Sign in:  director@pmo.local   /   Pmo@2026!
echo    Stop:     press Ctrl+C in this window
echo.
start "" /b cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
echo.
echo  The server stopped. If this was unexpected, the message above explains why.
pause
