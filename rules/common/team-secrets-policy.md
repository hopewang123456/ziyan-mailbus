# 团队密钥与 sudo 规范（全员必读）

> 同步目标：AgentMemory + 公告板 + 各 agent inbox notice  
> 最后更新：2026-06-16

## 禁止提交 git 的文件

| 路径 | 说明 |
|------|------|
| `docker-agents/.env.secrets` | WSL sudo 密码、本地密钥 |
| `docker-agents/.env` | Docker 环境变量（可能含 token） |
| `**/auth.json`、`**/.env` | 各框架 API Key |
| `mail/store/inbox/` | 可能含私密消息 |

**只有** `docker-agents/.env.secrets.example` 可提交（无真实密码）。

## sudo / 写文件权限

- mailbus `store/` 下部分文件由 **Docker mailbus 容器 root** 创建（如 `iterations/*.json`）
- 宿主机写入顺序：**直接写 → Docker 容器写 → `wsl-sudo.sh`（读 `.env.secrets`）**
- **禁止**在代码、公告、msg-results、聊天记录中明文写入 sudo 密码
- **禁止**把 `.env.secrets` 内容复制到 AgentMemory 或 inbox

## Agent 行为要求

1. 不要在 PR/commit 中包含 `.env.secrets`、`.env`、API Key
2. 发现密钥泄露 → 通知灵鉴 + 轮换密钥
3. 需要改 `store/iterations/` 时优先用：`docker exec docker-agents-mailbus-1 python3 /mailbus/tools/...`
4. 引用本规范：`rules/team-secrets-policy.md`（运行时同步到 `store/rules/`）

## 配置方法（运维/灵霄）

```bash
cp docker-agents/.env.secrets.example docker-agents/.env.secrets
# 编辑 SUDO_PASSWORD=...（勿提交 git）
bash docker-agents/wsl-sudo.sh echo ok
python3 mail/tools/ops/tools/ops/sync-team-rules.py --data-dir mail/store
```
