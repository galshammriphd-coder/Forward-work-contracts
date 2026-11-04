@echo off
REM ==========================================================
REM  Ghalib X Data Collector - Windows launcher
REM  First run: creates a virtual environment, installs the
REM  requirements and the Chromium browser for Playwright.
REM  Next runs: starts the application directly.
REM ==========================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Ghalib X Data Collector

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.11+ was not found. Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)

set "VPY=.venv\Scripts\python.exe"

if not exist ".venv\.installed" (
    echo [2/4] Installing requirements (first run only, a few minutes)...
    "%VPY%" -m pip install --upgrade pip
    "%VPY%" -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
    echo [3/4] Installing Chromium for Playwright...
    "%VPY%" -m playwright install chromium
    if errorlevel 1 (
        echo [WARN] Chromium download failed. You can still use Microsoft Edge:
        echo        Settings page - Browser - "Microsoft Edge".
    )
    echo installed> ".venv\.installed"
)

if /I "%1"=="test" (
    echo Running the test suite...
    "%VPY%" -m pytest -q tests
    pause
    exit /b %errorlevel%
)

echo [4/4] Starting Ghalib X Data Collector on http://localhost:8501 ...
start "" "http://localhost:8501"
"%VPY%" -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1
goto :eof

:fail
echo.
echo [ERROR] Setup failed. Check your internet connection and try again.
echo         Delete the .venv folder to restart the installation from scratch.
pause
exit /b 1
