@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === Slot Scraper Setup ===
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Please install it from https://www.python.org/downloads/
  echo IMPORTANT: check "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

if not exist venv (
  echo Creating virtual environment...
  python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing required packages...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install packages.
  pause
  exit /b 1
)

echo Installing Playwright browser (this can take a few minutes)...
python -m playwright install chromium
if errorlevel 1 (
  echo [ERROR] Failed to install the Playwright browser.
  pause
  exit /b 1
)

echo.
echo === Setup complete ===
echo Next steps (also written in README.md, in Japanese):
echo   1. Create a new GitHub repository (Private recommended, no README/gitignore added)
echo   2. Open publish.bat in a text editor and set REPO_URL to that repository's URL
echo   3. Double-click publish.bat to run it for the first time (it may open a browser to sign in to GitHub)
echo   4. In the GitHub repo, go to Settings - Pages and set Source to "main" / "/docs"
echo   5. Run schedule_task.ps1 to register the daily automatic run
echo.
pause
