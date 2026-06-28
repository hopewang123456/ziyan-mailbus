# Runbook — WSL Codex / bwrap / userns

> Postmortem 教训：Codex 容器在部分 WSL 内核上因 user namespace / bwrap 配置失败，表现为 agent 无法启动或 sandbox 报错。

## 症状

- `codex exec` 或 Docker codex-agent 容器内启动失败
- 日志含 `bwrap`、`user namespace`、`Operation not permitted`
- Web UI 可开但 exec 无响应

## 诊断

```bash
# WSL 内核 userns
sysctl kernel.unprivileged_userns_clone 2>/dev/null || true
grep -i usern /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || true

# 容器内
docker exec docker-agents-codex-lingxiao-1 id
docker exec docker-agents-codex-lingxiao-1 /usr/local/bin/render-codex-config.sh
```

## 缓解

1. **Docker Desktop**：Settings → Resources → WSL integration 启用 Ubuntu；重启 Docker。
2. **内核参数**（需管理员，仅当 userns 被禁用时）：
   ```bash
   echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/99-userns.conf
   sudo sysctl -p /etc/sysctl.d/99-userns.conf
   ```
3. **降级 sandbox**：Codex 配置中禁用 bwrap（见 `docker-agents/codex-agent/` 环境变量 `CODEX_*`）；仅 dev 环境。
4. **路径一致**：容器内 store 挂载为 `/mailbus/store`；`render-codex-config.sh` 已 `ln -sfn /mailbus/store ${PROJECT_DIR}/store`。勿手改 Windows 绝对路径进 config.toml。

## 验收

```bash
cd mail/docker-agents
bash setup-codex-agents.sh
curl -sf http://127.0.0.1:9240/ >/dev/null && echo OK lingxiao web
```

## WSL ↔ Windows localhost / Mailbus API（E2E）

Mailbus API 默认 **9814**（`MAILBUS_API_PORT` / `docker-agents/lib/mailbus-env.sh`）。

| 调用方 | 推荐 URL | 说明 |
|--------|----------|------|
| WSL bash | `http://127.0.0.1:9814` | `start-team.sh` / `mailbus-pipeline-e2e.sh` 同源 |
| Windows PowerShell | `http://localhost:9814` | Docker Desktop 端口转发到 WSL |
| WSL 访问 Windows 服务 | `http://$(grep nameserver /etc/resolv.conf \| awk '{print $2}'):9814` | 仅当 mailbus 跑在 Windows 原生进程时 |

**live E2E**（`verify-live-dali-e2e.py`）在 WSL 内执行；`MAILBUS_ROOT` 由 `mailbus-env.sh` 解析，勿硬编码 `E:\` 路径。

容器端口漂移（映射 9812 而 config 9814）时：

```bash
cd mail/docker-agents
docker compose up -d --force-recreate mailbus
curl -sf "http://127.0.0.1:${MAILBUS_API_PORT:-9814}/api/status"
```

## 相关

- `mail/docker-agents/codex-agent/render-codex-config.sh`
- `mail/config/mailbus.json` ports 段
- plan §10.7 WSL bwrap postmortem
