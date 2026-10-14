# Query all three scheduled tasks (pure ASCII, elevated).
$ErrorActionPreference = "Continue"
$log = Join-Path $PSScriptRoot "query-tasks-result.txt"
function Log($msg) { Add-Content -Path $log -Value $msg }
Remove-Item $log -ErrorAction SilentlyContinue

foreach ($t in @("MailbusPortProxy-Logon","MailbusPortProxy-Startup","MailbusPortProxy-Repeat")) {
    $info = schtasks /Query /TN $t /V /FO LIST 2>&1 | Out-String
    Log ("==== " + $t + " ====")
    Log $info
}

exit 0
