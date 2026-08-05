@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0VERIFY_PORTABLE.ps1"
if errorlevel 1 (
  echo.
  echo Portable verification FAILED.
  pause
  exit /b 1
)
echo.
echo Portable verification completed successfully.
pause
