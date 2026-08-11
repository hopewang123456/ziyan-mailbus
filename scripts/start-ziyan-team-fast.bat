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

call %PY% "%CD%\tools\mailbus.py" start --fast
set "RC=!ERRORLEVEL!"

echo.
if !RC! equ 0 (
  call %PY% "%CD%\tools\mailbus.py" recover health
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
