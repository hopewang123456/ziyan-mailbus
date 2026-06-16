# Docker 部署目录（已并入 ziyan-mailbus 仓库）

本目录为 mailbus 的 **Docker 团队部署层**，与仓库根目录的 Python 代码同属一个 git 仓库。

## 核心文件

- `docker-compose.yml` — 服务定义（mailbus / Hermes / OpenClaw / AgentMemory 等）
- `start-team.sh` / `stop-team.sh` — 一键启停
- `setup-container-proxy.sh` — Clash 开/关时代理同步
- `mailbus-pipeline-e2e.sh`、`monitor-regression.sh` — 回归脚本
- `.env.secrets.example` — sudo 密码占位（无真实密钥）

## 勿提交（已在仓库根 `.gitignore`）

- `docker-agents/.env` — API Key
- `docker-agents/.env.secrets` — WSL sudo 密码
- `docker-agents/.proxy-state`、`docker-agents/*.log`
- `store/`、`data/` — mailbus 运行时

## 提交前检查

```bash
git status   # 确认 .env / .env.secrets 未被 staged
grep -r "sk-" docker-agents/ --include='*.yml' --include='*.sh'
# 应只出现在 .env.example 占位符中
```

## 快速启动

```bash
bash docker-agents/start-team.sh
bash docker-agents/mailbus-pipeline-e2e.sh
```
