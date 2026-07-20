# 部署/修复 n8n mailbus-multi-publish workflow + 同步 webhook URL
# Usage: .\tools\setup-n8n.ps1 [-Reset]
param([switch]$Reset)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$composeDir = (python -c "import sys; sys.path.insert(0,'.'); from lib.env_bootstrap import load_mailbus_env, mailbus_paths; load_mailbus_env(); print(mailbus_paths()['compose_dir'].replace(chr(92),'/'))").Trim()

$script = if ($Reset) {
    "$composeDir/reset-n8n-workflow.sh"
} else {
    "$composeDir/ensure-n8n-workflow.sh"
}

Write-Host "[setup-n8n] running $script ..." -ForegroundColor Cyan
wsl -e bash $script
if ($LASTEXITCODE -ne 0 -and -not $Reset) {
    Write-Host "[setup-n8n] ensure failed, trying reset ..." -ForegroundColor Yellow
    wsl -e bash "$composeDir/reset-n8n-workflow.sh"
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

python tools/sync-n8n-url.py
exit $LASTEXITCODE
