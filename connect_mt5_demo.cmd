@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 (
  echo Could not open the SHREEK project folder. Run this command from PowerShell.
  exit /b 2
)
where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.9 or newer, then run from PowerShell.
  exit /b 2
)
py -3 -m execution.mt5_demo_bootstrap %*
exit /b %errorlevel%
