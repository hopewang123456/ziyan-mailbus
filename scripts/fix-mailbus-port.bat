@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Mailbus - Fix localhost port

cd /d "%~dp0.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   Fix Windows localhost -^> WSL port proxy
echo   Target: http://localhost:9814/
echo   Click Yes if UAC prompts
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

call %PY% "%CD%\tools\mailbus.py" portproxy
set "RC=!ERRORLEVEL!"

echo.
if !RC! equ 0 (
  call %PY% "%CD%\tools\mailbus.py" recover health
  set "RC=!ERRORLEVEL!"
)

if !RC! neq 0 (
  echo.
  echo [FAILED] Port fix exited with code !RC!
  echo   If UAC was denied, right-click and Run as administrator
  echo   Or run scripts\start-mailbus.bat / Desktop Start-Mailbus.bat first
) else (
  echo [OK] localhost:9814 is reachable
)

echo.
pause
exit /b !RC!
