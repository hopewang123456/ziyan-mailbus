@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title ziyan-mailbus - Stop
cd /d "%~dp0..\.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)
where wsl >nul 2>&1
if errorlevel 1 (
  python "%CD%\tools\mailbus.py" stop
) else (
  call "%CD%\scripts\_invoke-mailbus.bat" stop --windows
)
echo.
pause
