@echo off
setlocal

set "ROOT=%~dp0"
for %%I in ("%ROOT%chrome-extension") do set "EXTENSION=%%~fI"
for %%I in ("%ROOT%.skin-watcher-profile") do set "PROFILE=%%~fI"
set "BROWSER="

if not exist "%EXTENSION%\manifest.json" (
  echo Skin Watcher extension was not found.
  echo Expected: %EXTENSION%\manifest.json
  echo.
  echo Make sure this launcher is next to the chrome-extension folder.
  pause
  exit /b 1
)

for /d %%D in ("%LOCALAPPDATA%\ms-playwright\chromium-*") do (
  if exist "%%~fD\chrome-win64\chrome.exe" set "BROWSER=%%~fD\chrome-win64\chrome.exe"
  if exist "%%~fD\chrome-win\chrome.exe" set "BROWSER=%%~fD\chrome-win\chrome.exe"
)

if not defined BROWSER set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" (
  echo Chromium or Google Chrome was not found.
  echo Install Chrome or edit BROWSER in this launcher.
  pause
  exit /b 1
)

echo Starting Skin Watcher with: %BROWSER%
echo Extension folder: %EXTENSION%
echo.
echo If Skin Watcher does not appear, close every dedicated Skin Watcher browser window
echo and run this launcher again.
start "Skin Watcher Chrome" "%BROWSER%" ^
  "--user-data-dir=%PROFILE%" ^
  --disable-sync ^
  --enable-extensions ^
  "--disable-extensions-except=%EXTENSION%" ^
  "--load-extension=%EXTENSION%" ^
  --disable-translate ^
  --disable-background-timer-throttling ^
  --disable-renderer-backgrounding ^
  --disable-backgrounding-occluded-windows ^
  --disable-features=CalculateNativeWinOcclusion ^
  --no-first-run ^
  --no-default-browser-check ^
  --new-window "chrome://extensions/"

endlocal
