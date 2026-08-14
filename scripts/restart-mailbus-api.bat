@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title mailbus - Restart API
cd /d "%~dp0.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)
call "%CD%\tools\mailbus\restart.bat"
exit /b %ERRORLEVEL%
