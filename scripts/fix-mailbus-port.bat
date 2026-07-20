@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Mailbus - Fix localhost port

cd /d "%~dp0.."
if not exist "%CD%/tools/mailbus.py" (
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

where wsl >nul 2>&1
if errorlevel 1 (
  echo [ERROR] WSL not found. Start WSL Ubuntu first.
  pause
  exit /b 1
)

call "%~dp0_invoke-mailbus.bat" portproxy
set "RC=%ERRORLEVEL%"

echo.
if %RC% equ 0 (
  call "%~dp0_invoke-mailbus.bat" recover health
  set "RC=%ERRORLEVEL%"
)

if %RC% neq 0 (
  echo.
  echo [FAILED] Port fix exited with code %RC%
  echo   If UAC was denied, right-click and Run as administrator
  echo   Or run Start-Ziyan-AI-Team.bat first
) else (
  echo [OK] localhost:9814 is reachable
)

echo.
pause
exit /b %RC%
