@echo off
setlocal
call :run %*
set "SHREEK_EXIT_CODE=%errorlevel%"
echo.
echo SHREEK finished with exit code %SHREEK_EXIT_CODE%.
echo Exit code 2 means blocked or unavailable. It does not authorize an order retry.
if not defined SHREEK_NO_PAUSE pause
exit /b %SHREEK_EXIT_CODE%

:run
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
