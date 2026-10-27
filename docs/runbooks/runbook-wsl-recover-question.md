# Runbook — WSL 重启 / 休眠断连恢复

> SoT：`docs/question/runbooks/runbook-wsl-recover.md`（本文件）

休眠、`wsl --shutdown` 或 Docker Desktop 重启后，Windows `localhost:9814` 常超时（NAT / `wslrelay` stale），mailbus scan 与 live E2E 会失败。

## 症状

- `curl http://127.0.0.1:9814/api/status` 超时或连接拒绝
- WSL 内 mailbus 正常，Windows 浏览器 / PowerShell 访问失败
- Docker agent 容器 running 但 push 无响应

## 快速恢复（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File E:\ai_tools\scripts\wsl-recover.ps1
```

## WSL 内轻量恢复

```bash
cd mail/docker-agents
./wsl-recover.sh              # quick recover + scan
FULL=1 ./wsl-recover.sh       # full recover
SCAN=0 ./wsl-recover.sh       # recover 不跑 scan
```

等价 Python：

```bash
python mail/tools/mailbus.py recover quick --data-dir store
python mail/tools/mailbus.py recover full --data-dir store
```

## 验收

```bash
curl -sf "http://127.0.0.1:${MAILBUS_API_PORT:-9814}/api/status"
python -m bus scan
```

## 相关

- [`runbook-wsl-codex.md`](runbook-wsl-codex.md) — WSL localhost / Codex bwrap
- `docker-agents/wsl-recover.sh`
- `docker-agents/restart-watchdog.sh`
