# Compose 工作区占位（仅「未配置时」回落）

**解耦原则（全体框架相同）：** Hermes / OpenClaw / Codex / OpenCode / DSH 的运行时数据**不**搬进、不联进 mailbus。关联方式只有一种——在 **mailbus 配置**里写绝对路径：

- `docker-agents/.env`：`HERMES_DATA`、`OPENCLAW_WORKSPACE`、`CODEX_*`、`OPENCODE_ROOT`、`DSH_WORKSPACE`…
- 或设置页 / 实例 `install_path`

本目录空文件夹 = compose **未设环境变量**时的无害占位：

| 环境变量 | 未设置时的回落 |
|----------|----------------|
| `HERMES_DATA` | `./workspaces/hermes-data` |
| `OPENCLAW_WORKSPACE` | `./workspaces/openclaw` |
| `CODEX_WORKSPACE` | `./workspaces/codex` |
| `CODEX_REVIEW_WORKSPACE` | `./workspaces/codex-review` |
| `CODEX_SKILLS` | `./workspaces/codex-skills` |
| `OPENCODE_ROOT` | `./workspaces/opencode` |
| `DSH_WORKSPACE` | `./workspaces/dsh` |

**不要：** junction/拷贝 Agent 树进本目录；已提交 yml 写死 `../openclaw_space` / `../../Agent/docker/...`。

**要：** `.env` / 设置页写你机器上的真实绝对路径（可以是 Agent 树——那是配置关联）。

样例：`docker-agents/.env.example` → 复制为 `docker-agents/.env`。

`migrate_compose_workspaces.py` 仅可选「主动镜像到仓内」；解耦不要求。
