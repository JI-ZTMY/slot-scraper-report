@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem === Before the first run, replace this with the URL of the GitHub repo you created ===
set REPO_URL=https://github.com/JI-ZTMY/slot-scraper-report.git
rem =======================================================================================

if not exist venv (
  echo [ERROR] Setup has not been run yet. Please run setup_windows.bat first.
  pause
  exit /b 1
)

call venv\Scripts\activate.bat

echo Fetching data...
python src\run_all.py
if errorlevel 1 (
  echo [WARNING] There were errors during scraping. Check the log above. Continuing to publish the report anyway.
)

if not exist ".git" (
  echo Initializing git repository...
  git init
  git checkout -b main
  git remote add origin %REPO_URL%
)

git add docs config
git commit -m "Update report"
if errorlevel 1 (
  echo Nothing changed, skipped commit.
)

echo Pushing to GitHub...
git push -u origin main
if errorlevel 1 (
  echo [ERROR] git push failed. Check that REPO_URL is correct and that you're signed in to GitHub.
  pause
  exit /b 1
)

echo.
echo === Done ===
echo (First time only) In the GitHub repo, go to Settings - Pages and set Source to "main" / "/docs".
pause
