# 重启 mailbus 容器 — Windows 薄包装；Linux 请用：
#   python tools/mailbus.py docker restart-mailbus
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$py = $null
foreach ($name in @("python", "python3", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { Write-Host "[ERROR] python not found"; exit 2 }
& $py tools/mailbus.py docker restart-mailbus
exit $LASTEXITCODE
