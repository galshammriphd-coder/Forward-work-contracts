@echo off
REM ==========================================================
REM  Ghalib X Data Collector - Windows launcher
REM  First run : creates .venv, installs requirements + Chromium
REM  Next runs : starts the application directly
REM  Setup output is written to logs\setup_log.txt
REM  NOTE: no parentheses inside IF blocks (they break cmd.exe)
REM ==========================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Ghalib X Data Collector
if not exist "logs" mkdir "logs"
set "LOG=%~dp0logs\setup_log.txt"
echo ===== %date% %time% ===== >> "%LOG%"

echo.
echo   Ghalib X Data Collector
echo   Folder: %~dp0
echo.

REM ---------- 1. find a working Python 3.11+ ----------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :have_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :have_python

echo [ERROR] Python 3.11 or newer was not found.
echo.
echo   1. Download Python from https://www.python.org/downloads/
echo   2. During installation tick "Add python.exe to PATH"
echo   3. Close this window and run run_windows.bat again
echo.
echo   If Python is already installed: open Windows Settings, search for
echo   "App execution aliases" and turn OFF python.exe and python3.exe
echo   - these are Microsoft Store shortcuts, not real Python.
echo [ERROR] python not found >> "%LOG%"
goto :fail

:have_python
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo   Using %PYVER%
echo Using %PYVER% >> "%LOG%"

REM ---------- 2. virtual environment ----------
set "VPY=%~dp0.venv\Scripts\python.exe"
if exist "%VPY%" goto :have_venv
echo.
echo [1/4] Creating virtual environment .venv ...
%PY% -m venv "%~dp0.venv" >> "%LOG%" 2>&1
if errorlevel 1 goto :venv_failed
:have_venv

REM ---------- 3. install requirements once ----------
if exist "%~dp0.venv\.installed" goto :run_app
echo.
echo [2/4] Installing requirements - first run only, 5 to 10 minutes...
echo       Please wait, do not close this window.
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
echo [3/4] Installing Chromium browser for Playwright...
"%VPY%" -m playwright install chromium
if errorlevel 1 echo [WARN] Chromium download failed. In the app open Settings and choose Microsoft Edge.
echo installed> "%~dp0.venv\.installed"

:run_app
if /I "%~1"=="test" goto :run_tests

echo.
echo [4/4] Starting the application on http://localhost:8501
echo       Keep this window open while you use the platform.
echo       To stop the platform close this window.
echo.
start "" "http://localhost:8501"
"%VPY%" -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1
echo.
echo The application has stopped. If this was unexpected, read the messages above
echo or the file logs\ghalib.log
pause
exit /b 0

:run_tests
"%VPY%" -m pytest -q tests
pause
exit /b 0

:venv_failed
echo [ERROR] Could not create the virtual environment. Details in logs\setup_log.txt
goto :fail

:pip_failed
echo.
echo [ERROR] Installing the requirements failed.
echo   - Check your internet connection
echo   - Delete the .venv folder and run run_windows.bat again
echo   - Details are in logs\setup_log.txt
goto :fail

:fail
echo.
pause
exit /b 1
