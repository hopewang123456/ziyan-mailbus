@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Ziyan AI Team - Stop

cd /d "%~dp0.."
if not exist "%CD%/tools/mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   Ziyan AI Team - Stop all containers
echo ==========================================
echo.

where wsl >nul 2>&1
if errorlevel 1 (
  echo [ERROR] WSL not found
  pause
  exit /b 1
)

call "%~dp0_invoke-mailbus.bat" stop
set "RC=%ERRORLEVEL%"

if %RC% neq 0 (
  echo.
  echo [FAILED] Stop exited with code %RC%
) else (
  echo.
  echo [OK] All agent containers stopped
)

echo.
pause
exit /b %RC%
