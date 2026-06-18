@echo off
setlocal
cd /d "%~dp0"

echo PirateSwap Skin Watcher
echo =======================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" was not found.
  echo Install Python 3.11 or newer from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is enabled during install.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)

echo Installing/updating Python packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Installing/updating Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto error

echo Opening UI...
".venv\Scripts\python.exe" gui.py
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo Something failed. Check the messages above.
pause
exit /b 1
