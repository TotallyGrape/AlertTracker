@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-services.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. See the message above and the .logs folder.
  pause
  exit /b 1
)
endlocal
