@echo off
setlocal
cd /d "%~dp0"
title Local Skill Exchange Platform

echo ========================================
echo  LOCAL SKILL EXCHANGE PLATFORM
echo ========================================
echo.
echo Starting application...

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
) else (
  py -3 -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install Python 3.11 or newer, then run START.bat again.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=py -3"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :failed
)

echo Checking required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

if not exist "instance" mkdir "instance"
if not exist "app\static\uploads" mkdir "app\static\uploads"

echo.
echo Website:
echo http://127.0.0.1:5000
echo.
echo Press CTRL+C to stop the server.
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"
".venv\Scripts\python.exe" run.py
exit /b %errorlevel%

:failed
echo.
echo Setup failed. Check your internet connection and Python installation.
pause
exit /b 1
