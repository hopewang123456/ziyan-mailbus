@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "MAILBUS_ROOT=%CD%"
set "MAILBUS_PY=%CD%\tools\mailbus.py"

if not exist "%MAILBUS_PY%" (
  echo [ERROR] Missing %MAILBUS_PY%
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 goto try_py
python "%MAILBUS_PY%" %*
exit /b %ERRORLEVEL%

:try_py
where py >nul 2>&1
if errorlevel 1 goto try_mailbus
py -3 "%MAILBUS_PY%" %*
exit /b %ERRORLEVEL%

:try_mailbus
where mailbus >nul 2>&1
if errorlevel 1 goto no_cli
mailbus %*
exit /b %ERRORLEVEL%

:no_cli
echo [ERROR] Python or mailbus CLI not found
echo         Try: pip install -e "%MAILBUS_ROOT%"
exit /b 1
