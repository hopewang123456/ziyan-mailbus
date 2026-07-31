# Windows helpers (port forwarding)

Scripts here are **Windows-only**. Native Linux/macOS does not need them.

| Script | Purpose |
|--------|---------|
| `fix-wsl-localhost.ps1` | Refresh `netsh interface portproxy` so Windows `127.0.0.1` reaches services listening inside WSL (mailbus `:9814`, agent UIs, OpenClaw, …). May prompt UAC. |

## When to use

Use this when the **team stack runs in WSL/Docker**, but you open the browser / desktop clients **on Windows**. WSL IP changes and stale `wslrelay` often break localhost; this script re-binds portproxy.

```powershell
# From repo root (admin UAC may appear)
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\fix-wsl-localhost.ps1

# Or via unified CLI
python tools/mailbus.py portproxy
```

Thin wrappers: `scripts/fix-mailbus-port.bat`, `tools/mailbus/fix-port.bat`.

## Not needed on Linux / macOS

On Linux or macOS, bind/serve on the host (or Docker published ports). `python tools/mailbus.py portproxy` is a **no-op**.

---

# Windows 辅助（端口转发）

本目录脚本**仅 Windows**。原生 Linux/macOS 不需要。

| 脚本 | 作用 |
|------|------|
| `fix-wsl-localhost.ps1` | 刷新 `netsh interface portproxy`，让 Windows 上的 `127.0.0.1` 能访问 WSL 内监听的服务（mailbus `:9814`、各 Agent UI、OpenClaw 等）。可能弹出 UAC。 |

团队跑在 **WSL/Docker**、浏览器在 **Windows** 时使用。WSL IP 变化或 `wslrelay` 过期会导致 localhost 不通，本脚本重建转发。

Linux/macOS 上 `portproxy` 为空操作，直接 `python tools/mailbus.py start` / `serve` 即可。
