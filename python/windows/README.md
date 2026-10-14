# Windows helpers (port forwarding)

> **Scope:** companion to **device-bridge** (phone ↔ host `:9814`). Not required for mailbus config-plane / compose decoupling. Safe to keep in the same branch as device-bridge; omit from a config-only cherry-pick.

Scripts here are **Windows-only**. Native Linux/macOS does not need them.

| Script | Purpose |
|--------|---------|
| `rebuild-portproxy.ps1` | **一键重建全部转发**：唤醒 WSL → 等 WSL IP → 重建 `127.0.0.1` 规则 + Tailscale `:9814` 规则。幂等，可反复执行。 |
| `fix-wsl-localhost.ps1` | 只刷新 `127.0.0.1` → WSL（本机浏览器访问）。可能弹 UAC。 |
| `expose-device-bridge.ps1` | 只暴露 `:9814` 给手机（Tailscale / `-Lan`）。`rebuild-portproxy.ps1` 已包含此能力。 |
| `clear-portproxy.ps1` | 清空全部 portproxy 规则（排障/回滚用）。 |
| `create-tasks.ps1` / `query-tasks.ps1` | 创建 / 查询「重启后自动恢复」的计划任务。 |

## 重启后自动恢复（计划任务）

WSL IP 每次重启会漂移，导致 portproxy 失效。已注册 **3 个计划任务**，重启后自动重建转发，无需手动重跑：

| 任务名 | 触发 | 说明 |
|--------|------|------|
| `MailbusPortProxy-Startup` | 开机（SYSTEM，延迟 2 分钟） | 覆盖电脑开机场景 |
| `MailbusPortProxy-Logon` | 用户登录（延迟 1 分钟） | 覆盖日常登录场景 |
| `MailbusPortProxy-Repeat` | 每 5 分钟 | 覆盖 `wsl --shutdown` 单独重启场景（幂等，IP 未变则快速跳过） |

三个任务都调用 `rebuild-portproxy.ps1`，脚本会自动唤醒 WSL 并等待其 IP 就绪，所以「电脑/WSL 重启」后无需手动干预，最多约 5 分钟自动恢复。

```powershell
# 查看任务
schtasks /Query /TN "MailbusPortProxy-Logon"
schtasks /Query /TN "MailbusPortProxy-Startup"
schtasks /Query /TN "MailbusPortProxy-Repeat"

# 手动重建一次（等价于计划任务做的事，需要 UAC 提权）
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\rebuild-portproxy.ps1
```

手机访问路径：`http://<电脑 Tailscale 100.x>:9814/api/health`。

## 镜像网络模式（已回滚）

曾尝试将 WSL 切到 `networkingMode=mirrored` 以彻底消除 portproxy，但发现 mailbus 全家桶在该模式下出现 Docker 容器间 DNS 解析失败（`iii-engine` 无法解析），触发 agentmemory watchdog 死循环重启，端口发布不稳定。**已回滚到 NAT 模式**，改用上述计划任务自愈方案。当前 `.wslconfig` 保持 `localhostForwarding=true`（NAT）。

## Not needed on Linux / macOS

On Linux or macOS, bind/serve on the host (or Docker published ports). `python tools/mailbus.py portproxy` is a **no-op**.

---

# Windows 辅助（端口转发）

本目录脚本**仅 Windows**。原生 Linux/macOS 不需要。

| 脚本 | 作用 |
|------|------|
| `rebuild-portproxy.ps1` | **一键重建全部转发**：唤醒 WSL → 等 WSL IP → 重建 `127.0.0.1` 规则 + Tailscale `:9814` 规则。幂等，可反复执行。 |
| `fix-wsl-localhost.ps1` | 只刷新 `127.0.0.1` → WSL（本机浏览器访问）。可能弹 UAC。 |
| `expose-device-bridge.ps1` | 只暴露 `:9814` 给手机（Tailscale / `-Lan`）。`rebuild-portproxy.ps1` 已包含此能力。 |
| `clear-portproxy.ps1` | 清空全部 portproxy 规则（排障/回滚用）。 |
| `create-tasks.ps1` / `query-tasks.ps1` | 创建 / 查询「重启后自动恢复」的计划任务。 |

## 重启后自动恢复（计划任务）

WSL IP 每次重启会漂移，导致 portproxy 失效。已注册 **3 个计划任务**，重启后自动重建转发，无需手动重跑：

| 任务名 | 触发 | 说明 |
|--------|------|------|
| `MailbusPortProxy-Startup` | 开机（SYSTEM，延迟 2 分钟） | 覆盖电脑开机场景 |
| `MailbusPortProxy-Logon` | 用户登录（延迟 1 分钟） | 覆盖日常登录场景 |
| `MailbusPortProxy-Repeat` | 每 5 分钟 | 覆盖 `wsl --shutdown` 单独重启场景（幂等，IP 未变则快速跳过） |

三个任务都调用 `rebuild-portproxy.ps1`，脚本会自动唤醒 WSL 并等待其 IP 就绪，所以「电脑/WSL 重启」后无需手动干预，最多约 5 分钟自动恢复。

```powershell
# 查看任务
schtasks /Query /TN "MailbusPortProxy-Logon"
schtasks /Query /TN "MailbusPortProxy-Startup"
schtasks /Query /TN "MailbusPortProxy-Repeat"

# 手动重建一次（等价于计划任务做的事，需要 UAC 提权）
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\rebuild-portproxy.ps1
```

手机访问路径：`http://<电脑 Tailscale 100.x>:9814/api/health`。

## 镜像网络模式（已回滚）

曾尝试将 WSL 切到 `networkingMode=mirrored` 以彻底消除 portproxy，但发现 mailbus 全家桶在该模式下出现 Docker 容器间 DNS 解析失败（`iii-engine` 无法解析），触发 agentmemory watchdog 死循环重启，端口发布不稳定。**已回滚到 NAT 模式**，改用上述计划任务自愈方案。当前 `.wslconfig` 保持 `localhostForwarding=true`（NAT）。
