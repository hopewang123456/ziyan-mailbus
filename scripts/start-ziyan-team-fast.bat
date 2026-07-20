@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Ziyan AI Team - Fast Start

cd /d "%~dp0.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   Ziyan AI Team - FAST Start
echo   skip: smoke / Ollama ensure / LLM bootstrap
echo   mailbus: http://localhost:9814/
echo ==========================================
echo.

where wsl >nul 2>&1
if errorlevel 1 (
  echo [ERROR] WSL not found
  pause
  exit /b 1
)

call "%~dp0_invoke-mailbus.bat" start --windows --fast
set "RC=!ERRORLEVEL!"

echo.
if !RC! equ 0 (
  call "%~dp0_invoke-mailbus.bat" recover health
  set "RC=!ERRORLEVEL!"
)

if !RC! neq 0 (
  echo.
  echo [FAILED] Fast start exited with code !RC!
  echo   Try full Start-Ziyan-AI-Team.bat or Fix-Mailbus-Port.bat
) else (
  echo [OK] mailbus ready - open http://localhost:9814/
)

echo.
pause
exit /b !RC!
