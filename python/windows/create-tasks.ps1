# Create scheduled tasks to auto-rebuild portproxy (pure ASCII).
$ErrorActionPreference = "Continue"
$log = Join-Path $PSScriptRoot "create-tasks-result.txt"
function Log($msg) { Add-Content -Path $log -Value $msg }
Remove-Item $log -ErrorAction SilentlyContinue

$tr = 'powershell -NoProfile -ExecutionPolicy Bypass -File "E:\ai_tools\mailbus\windows\rebuild-portproxy.ps1"'

$r1 = schtasks /Create /TN "MailbusPortProxy-Logon" /TR $tr /SC ONLOGON /DELAY 0001:00 /RL HIGHEST /F 2>&1 | Out-String
Log ("[logon] " + $r1.Trim())

$r2 = schtasks /Create /TN "MailbusPortProxy-Startup" /TR $tr /SC ONSTART /RU SYSTEM /DELAY 0002:00 /RL HIGHEST /F 2>&1 | Out-String
Log ("[startup] " + $r2.Trim())

$r3 = schtasks /Create /TN "MailbusPortProxy-Repeat" /TR $tr /SC MINUTE /MO 5 /RL HIGHEST /F 2>&1 | Out-String
Log ("[repeat] " + $r3.Trim())

$list = schtasks /Query /TN "MailbusPortProxy-Logon" /V /FO LIST 2>&1 | Out-String
Log ("[verify-logon] " + $list.Trim())

exit 0
