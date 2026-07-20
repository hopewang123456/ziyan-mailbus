@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Ziyan AI Team - Start

cd /d "%~dp0.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  echo         Expected: E:\ai_tools\mail
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   Ziyan AI Team - Start
echo   mailbus: http://localhost:9814/
echo ==========================================
echo.

where wsl >nul 2>&1
if errorlevel 1 (
  echo [ERROR] WSL not found. Install Windows Subsystem for Linux first.
  pause
  exit /b 1
)

call "%~dp0_invoke-mailbus.bat" start --windows
set "RC=!ERRORLEVEL!"

echo.
if !RC! equ 0 (
  call "%~dp0_invoke-mailbus.bat" recover health
  set "RC=!ERRORLEVEL!"
)

if !RC! neq 0 (
  echo.
  echo [FAILED] Start exited with code !RC!
  echo   1. Run Fix-Mailbus-Port.bat as admin if UAC prompts
  echo   2. Log: wsl -d Ubuntu -e tail -50 /tmp/start-team.log
  echo   3. Doctor: python "%CD%\tools\mailbus.py" doctor
  echo   4. Health: python "%CD%\tools\mailbus.py" recover health
  echo   5. Windows capture: type "%CD%\run\last-start-windows.txt"
) else (
  echo [OK] mailbus ready - open http://localhost:9814/
)

echo.
echo Press any key to close...
pause >nul
exit /b !RC!
