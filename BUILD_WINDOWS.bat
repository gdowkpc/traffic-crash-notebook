@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1" -Clean
if errorlevel 1 (
  echo.
  echo Windows build FAILED. Review the messages above.
  pause
  exit /b 1
)
echo.
echo Windows portable build completed successfully.
pause
