# 全自动：防睡眠 → ComfyUI → 12 人肖像+真眨眼动图（逐人，失败重启 ComfyUI）
param(
    [switch]$MotionOnly,
    [string[]]$Agents = @()
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$keepAwake = Start-Process powershell -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "keep-awake.ps1")
) -PassThru -WindowStyle Hidden

function Stop-KeepAwake {
    if ($keepAwake -and -not $keepAwake.HasExited) {
        Stop-Process -Id $keepAwake.Id -Force -ErrorAction SilentlyContinue
    }
    & (Join-Path $PSScriptRoot "keep-awake.ps1") -Stop 2>$null
}

$log = Join-Path $Root "store\logs\portraits-batch.log"
"=== $(Get-Date -Format o) batch start ===" | Tee-Object -FilePath $log -Append

try {
    wsl bash -lc "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh" 2>&1 | Tee-Object -FilePath $log -Append
    python (Join-Path $PSScriptRoot "sync-comfyui-url.py") 2>&1 | Tee-Object -FilePath $log -Append

    if ($Agents.Count -eq 0) {
        $Agents = @(
            "lingzhao", "lingjin", "lingxi", "lingtuo", "lingjian", "lingyan",
            "lingxun", "lingxiao", "dali", "xiaoqi", "yige", "lingzhang"
        )
    }

    $ok = 0
    foreach ($a in $Agents) {
        Write-Host "`n======== $a ========" | Tee-Object -FilePath $log -Append
        $args = @((Join-Path $PSScriptRoot "gen-agent-portraits.py"), $a, "-f")
        if ($MotionOnly) { $args += "--motion-only" }
        python @args 2>&1 | Tee-Object -FilePath $log -Append
        if ($LASTEXITCODE -ne 0) {
            wsl bash -lc "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh" 2>&1 | Tee-Object -FilePath $log -Append
            python (Join-Path $PSScriptRoot "sync-comfyui-url.py") 2>&1 | Tee-Object -FilePath $log -Append
            python @args 2>&1 | Tee-Object -FilePath $log -Append
        }
        if ($LASTEXITCODE -eq 0) { $ok++ }
        Start-Sleep -Seconds 15
    }
    "=== done $ok/$($Agents.Count) ===" | Tee-Object -FilePath $log -Append
}
finally {
    Stop-KeepAwake
}
