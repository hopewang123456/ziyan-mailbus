@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title ziyan-mailbus - Stop

cd /d "%~dp0.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)

where python >nul 2>&1
if not errorlevel 1 (
  python "%CD%\tools\mailbus.py" stop
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
  )
  py -3 "%CD%\tools\mailbus.py" stop
)
echo.
pause
