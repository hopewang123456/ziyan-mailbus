# Clear all portproxy rules after switching WSL to mirrored networking.
# Mirrored mode maps Docker ports directly onto Windows interfaces, so
# portproxy (which pointed at the old NAT WSL IP) is now redundant/broken.
$ErrorActionPreference = "Continue"

$log = Join-Path $PSScriptRoot "clear-portproxy-result.txt"
function Log($msg) { Add-Content -Path $log -Value $msg }
Remove-Item $log -ErrorAction SilentlyContinue

# 1) netsh reset clears normal v4tov4/v4tov6 rules
netsh interface portproxy reset 2>&1 | Out-Null
Log ("[clear-portproxy] netsh reset done")

# 2) Remove the whole registry key to also drop any malformed entries
reg delete "HKLM\SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp" /f 2>&1 | Out-Null
Log ("[clear-portproxy] reg delete done")

# 3) Restart the ip helper service so it re-reads the (now empty) proxy table
Restart-Service iphlpsvc -Force 2>&1 | Out-Null
Log ("[clear-portproxy] iphlpsvc restarted")

# 4) Show remaining rules
$left = netsh interface portproxy show v4tov4 2>&1 | Out-String
Log ("[clear-portproxy] remaining:" + $left.Trim())

exit 0
