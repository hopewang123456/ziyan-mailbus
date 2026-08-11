@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Mailbus - Fix localhost port
cd /d "%~dp0..\.."
if not exist "%CD%\tools\mailbus.py" (
  echo [ERROR] mailbus root not found: %CD%
  pause
  exit /b 1
)
call "%CD%\scripts\fix-mailbus-port.bat"
exit /b %ERRORLEVEL%
