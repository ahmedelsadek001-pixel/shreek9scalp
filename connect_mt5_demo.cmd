@echo off
setlocal
cd /d "%~dp0"
if not defined LOCALAPPDATA (
  echo Windows LOCALAPPDATA is required.
  exit /b 2
)
set "SHREEK_RUNTIME=%LOCALAPPDATA%\SHREEK\mt5-runtime"
if not exist "%SHREEK_RUNTIME%\Scripts\python.exe" (
  py -3 -m venv "%SHREEK_RUNTIME%"
  if errorlevel 1 exit /b 2
)
"%SHREEK_RUNTIME%\Scripts\python.exe" -m pip install MetaTrader5
if errorlevel 1 exit /b 2
"%SHREEK_RUNTIME%\Scripts\python.exe" -m execution.mt5_demo_windows_cli %*
exit /b %errorlevel%
