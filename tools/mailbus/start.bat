@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title ziyan-mailbus - Start
cd /d "%~dp0..\.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)
echo.
echo ==========================================
echo   ziyan-mailbus
echo   API: http://localhost:9814/
echo ==========================================
echo.
where python >nul 2>&1
if not errorlevel 1 (
  python "%CD%\tools\mailbus.py" start
  set "RC=!ERRORLEVEL!"
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
  )
  py -3 "%CD%\tools\mailbus.py" start
  set "RC=!ERRORLEVEL!"
)
if !RC! equ 0 (echo [OK] Start finished.) else (echo [FAILED] exit code !RC!)
echo.
pause
exit /b !RC!
