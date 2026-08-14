@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title mailbus - Restart API
cd /d "%~dp0..\.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   Restart mailbus API container
echo   then recover health / portproxy
echo ==========================================
echo.

where python >nul 2>&1
if not errorlevel 1 (
  set "PY=python"
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
  )
  set "PY=py -3"
)

call %PY% "%CD%\tools\mailbus.py" docker restart-mailbus
set "RC=!ERRORLEVEL!"

if !RC! equ 0 (
  call %PY% "%CD%\tools\mailbus.py" portproxy
  call %PY% "%CD%\tools\mailbus.py" recover health
  set "RC=!ERRORLEVEL!"
)

echo.
if !RC! equ 0 (
  echo [OK] mailbus API restarted - http://localhost:9814/
) else (
  echo [FAILED] exit code !RC!
  echo   Try: scripts\start-mailbus.bat or Desktop Start-Mailbus.bat
)
echo.
pause
exit /b !RC!
