# 一键：防睡眠 → 同步 ComfyUI → 重启 Mailbus → 同步资料卡 → 生成肖像 → API 冒烟
param(
    [switch]$SkipPortraits,
    [switch]$SkipComfyui,
    [string[]]$PortraitAgents = @()
)

$ErrorActionPreference = "Stop"
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

try {
    Write-Host "== [1/6] 防睡眠已启动 PID $($keepAwake.Id) =="

    if (-not $SkipComfyui) {
        Write-Host "== [2/6] 同步 ComfyUI URL =="
        python (Join-Path $PSScriptRoot "sync-comfyui-url.py")
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ComfyUI 不可达，尝试 WSL 启动..."
            wsl bash -lc "cd /mnt/e/ai_tools/mail/docker-agents && bash start-comfyui-gpu.sh"
            python (Join-Path $PSScriptRoot "sync-comfyui-url.py")
        }
        python (Join-Path $PSScriptRoot "smoke-comfyui-gpu.py")
    } else {
        Write-Host "== [2/6] 跳过 ComfyUI =="
    }

    Write-Host "== [3/6] 重启 Mailbus =="
    python (Join-Path $PSScriptRoot "restart-mailbus.py") --port 9814

    Write-Host "== [4/6] 同步 profile-cards =="
    python (Join-Path $PSScriptRoot "sync-profile-cards.py")

    if (-not $SkipPortraits) {
        Write-Host "== [5/6] 生成 Agent 肖像 (ComfyUI) =="
        $args = @((Join-Path $PSScriptRoot "gen-agent-portraits.py"), "-f")
        if ($PortraitAgents.Count -gt 0) { $args += $PortraitAgents }
        python @args
    } else {
        Write-Host "== [5/6] 跳过肖像生成 =="
    }

    Write-Host "== [6/6] Dashboard API 冒烟 =="
    python (Join-Path $PSScriptRoot "smoke-dashboard-api.py")
    Write-Host "`n✅ 流水线完成。请在浏览器打开 http://127.0.0.1:9814 验证 Agent 资料卡 UI。"
}
finally {
    Stop-KeepAwake
}
