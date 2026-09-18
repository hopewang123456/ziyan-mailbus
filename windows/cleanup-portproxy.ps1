# Cleanup: remove redundant portproxy scheduled tasks + Tailscale 9814 rule.
# - Deletes the 3 scheduled tasks that pop a visible PowerShell window.
# - Removes the Tailscale :9814 portproxy rule (phone/glasses now use Serve/Funnel).
# - Keeps localhost rules (they are the wslrelay fallback for browser access to WSL).
# Pure ASCII to avoid PS5.1 encoding issues.
$ErrorActionPreference = "Continue"
$log = Join-Path $PSScriptRoot "cleanup-result.txt"
function Log($msg) { Add-Content -Path $log -Value $msg }
Remove-Item $log -ErrorAction SilentlyContinue

# 1) Remove the 3 scheduled tasks (the source of the popup windows)
$t1 = schtasks /Delete /TN "MailbusPortProxy-Logon" /F 2>&1 | Out-String
Log ("[cleanup] delete Logon: " + $t1.Trim())
$t2 = schtasks /Delete /TN "MailbusPortProxy-Startup" /F 2>&1 | Out-String
Log ("[cleanup] delete Startup: " + $t2.Trim())
$t3 = schtasks /Delete /TN "MailbusPortProxy-Repeat" /F 2>&1 | Out-String
Log ("[cleanup] delete Repeat: " + $t3.Trim())

# 2) Remove the Tailscale 9814 rule (redundant: phone uses Serve, glasses use Funnel)
netsh interface portproxy delete v4tov4 listenport=9814 listenaddress=100.64.141.78 2>&1 | Out-Null
Log "[cleanup] deleted Tailscale 9814 rule"

# 3) Keep localhost rules on purpose (browser -> WSL fallback)

# 4) Verify
$left = schtasks /Query /FO LIST 2>&1 | Select-String "MailbusPortProxy" | Out-String
Log ("[cleanup] remaining tasks: " + $left.Trim())
$rules = netsh interface portproxy show v4tov4 2>&1 | Out-String
Log ("[cleanup] remaining portproxy:" + $rules.Trim())

exit 0
