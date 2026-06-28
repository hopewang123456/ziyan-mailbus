# 防止 Windows 锁屏/睡眠，避免 WSL 与长任务中断
param(
    [switch]$Stop,
    [int]$Minutes = 0  # 0 = 直到 Stop 或进程退出
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PowerKeepAwake {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
    public const uint ES_AWAYMODE_REQUIRED = 0x00000040;
}
"@

$flagFile = Join-Path $env:TEMP "mailbus-keep-awake.pid"

if ($Stop) {
    [PowerKeepAwake]::SetThreadExecutionState([PowerKeepAwake]::ES_CONTINUOUS) | Out-Null
    if (Test-Path $flagFile) { Remove-Item $flagFile -Force }
    Write-Host "[keep-awake] 已恢复系统默认电源策略"
    exit 0
}

$state = [PowerKeepAwake]::ES_CONTINUOUS -bor [PowerKeepAwake]::ES_SYSTEM_REQUIRED -bor [PowerKeepAwake]::ES_DISPLAY_REQUIRED
[PowerKeepAwake]::SetThreadExecutionState($state) | Out-Null
$PID | Set-Content $flagFile
Write-Host "[keep-awake] 已阻止锁屏/睡眠 (PID $PID)"

if ($Minutes -gt 0) {
    Start-Sleep -Seconds ($Minutes * 60)
    [PowerKeepAwake]::SetThreadExecutionState([PowerKeepAwake]::ES_CONTINUOUS) | Out-Null
    if (Test-Path $flagFile) { Remove-Item $flagFile -Force }
    Write-Host "[keep-awake] 定时结束，已恢复"
}
