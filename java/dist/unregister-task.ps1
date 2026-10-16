# mailbus-j Windows remover: schtasks entry AND startup-folder launcher.
$ErrorActionPreference = "Continue"
Unregister-ScheduledTask -TaskName "mailbus-j-serve" -Confirm:$false -ErrorAction SilentlyContinue
$vbs = Join-Path ([Environment]::GetFolderPath("Startup")) "mailbus-j-serve.vbs"
if (Test-Path $vbs) { Remove-Item $vbs -Force; Write-Host "removed $vbs" }
Write-Host "removed mailbus-j-serve (if it existed)"
