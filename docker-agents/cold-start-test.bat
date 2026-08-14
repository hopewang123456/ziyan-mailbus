@echo off
chcp 65001 >nul
setlocal
set SCRIPT_DIR=%~dp0
if not defined MAILBUS_ROOT set "MAILBUS_ROOT=%SCRIPT_DIR%.."
for %%I in ("%MAILBUS_ROOT%") do set "MAILBUS_ROOT=%%~fI"
set "LOG=%SCRIPT_DIR%cold-start.log"
if not defined MAILBUS_WSL_ROOT (
  set "MAILBUS_WSL_ROOT=/mnt/<MAILBUS_ROOT>/mail"
)
title Cold Start Regression Test
echo ========================================== > "%LOG%"
echo   Cold Start Test - Mailbus >> "%LOG%"
echo   MAILBUS_ROOT=%MAILBUS_ROOT% >> "%LOG%"
echo   Started: %DATE% %TIME% >> "%LOG%"
echo ========================================== >> "%LOG%"

echo [1/4] Shutting down WSL...
echo [1/4] Shutting down WSL... >> "%LOG%"
wsl --shutdown
ping -n 9 127.0.0.1 >nul

echo [2/4] Starting team (mailbus start, no browser)...
echo [2/4] Starting team... >> "%LOG%"
wsl -d Ubuntu -e python3 %MAILBUS_WSL_ROOT%/tools/mailbus.py start >> "%LOG%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo [FAIL] mailbus start failed >> "%LOG%"
  exit /b 1
)

echo [3/4] Fixing Windows localhost ports...
powershell -NoProfile -ExecutionPolicy Bypass -File "%MAILBUS_ROOT%\windows\fix-wsl-localhost.ps1" >> "%LOG%" 2>&1

echo [4/4] Waiting 60s then smoke test...
ping -n 61 127.0.0.1 >nul
wsl -d Ubuntu bash -c "SMOKE_WAIT_SEC=0 python3 %MAILBUS_WSL_ROOT%/tools/mailbus.py smoke" >> "%LOG%" 2>&1
set ERR=%ERRORLEVEL%

echo. >> "%LOG%"
if %ERR% EQU 0 (
  echo [PASS] Cold start regression OK >> "%LOG%"
  echo [PASS] Cold start regression OK
) else (
  echo [FAIL] Cold start regression failed - exit %ERR% >> "%LOG%"
  echo [FAIL] Cold start regression failed - exit %ERR%
)
exit /b %ERR%
