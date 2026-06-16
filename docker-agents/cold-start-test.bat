@echo off
chcp 65001 >nul
set LOG=E:\ai_tools\docker-agents\cold-start.log
title Cold Start Regression Test
echo ========================================== > "%LOG%"
echo   Cold Start Test - ziyan AI team >> "%LOG%"
echo   Started: %DATE% %TIME% >> "%LOG%"
echo ========================================== >> "%LOG%"

echo [1/4] Shutting down WSL...
echo [1/4] Shutting down WSL... >> "%LOG%"
wsl --shutdown
ping -n 9 127.0.0.1 >nul

echo [2/4] Starting team (start-team.sh, no browser)...
echo [2/4] Starting team... >> "%LOG%"
wsl -d Ubuntu -e bash /mnt/e/ai_tools/mail/docker-agents/start-team.sh >> "%LOG%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo [FAIL] start-team failed >> "%LOG%"
  exit /b 1
)

echo [3/4] Fixing Windows localhost ports...
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\ai_tools\scripts\fix-wsl-localhost.ps1" >> "%LOG%" 2>&1

echo [4/4] Waiting 60s then smoke test...
ping -n 61 127.0.0.1 >nul
wsl -d Ubuntu bash -c "SMOKE_WAIT_SEC=0 bash /mnt/e/ai_tools/mail/docker-agents/smoke-test.sh" >> "%LOG%" 2>&1
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
