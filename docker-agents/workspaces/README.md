# Compose 工作区占位（仓内默认，不猜兄弟仓 Agent/docker）

`docker-compose.yml` 在未设置环境变量时回落到本目录下的子文件夹，例如：

| 环境变量 | 默认目录 |
|----------|----------|
| `HERMES_DATA` | `./workspaces/hermes-data` |
| `CODEX_WORKSPACE` | `./workspaces/codex` |
| `CODEX_REVIEW_WORKSPACE` | `./workspaces/codex-review` |
| `CODEX_SKILLS` | `./workspaces/codex-skills` |
| `DSH_WORKSPACE` | `./workspaces/dsh` |

生产/本机请在 `docker-agents/.env`（可从 `.env.example` 复制）或设置页写入真实绝对路径。
挂机专属卷用 `docker-compose.override.yml`（gitignore）：从 `docker-compose.override.example.yml` 复制，**只写 `${MAILBUS_HOST_ROOT}` / `${OPENCLAW_WORKSPACE}` 等变量**，绝对路径放进 `.env`，勿写进 yml。

若 `.env` 仍指向兄弟仓 `Agent/docker/...`，迁到本目录：

```bash
python tools/ops/migrate_compose_workspaces.py --dry-run
python tools/ops/migrate_compose_workspaces.py --link --update-env
```

`--link` 在 Windows 建目录联接（不复制数据）；`--copy` 做完整拷贝。脚本只读现有 `.env` 源路径，不猜布局。

勿再使用 `../../Agent/docker/...` 作为默认。
