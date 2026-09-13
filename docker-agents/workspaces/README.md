# Compose 工作区占位（仅「未配置时」回落）

**解耦原则：** Agent 运行时数据不搬进、不联进 mailbus。关联方式只有一种——在 **mailbus 配置**里写绝对路径：

- `docker-agents/.env`（compose 挂卷）：`OPENCLAW_WORKSPACE`、`CODEX_WORKSPACE`、…
- 或设置页 / `store/config.json` 实例 `install_path` 等

本目录下的空文件夹只给 `docker-compose.yml` 在**环境变量未设**时当无害占位，例如：

| 环境变量 | 未设置时的回落 |
|----------|----------------|
| `HERMES_DATA` | `./workspaces/hermes-data` |
| `CODEX_WORKSPACE` | `./workspaces/codex` |
| `OPENCLAW_WORKSPACE` | （compose 里对应 `${OPENCLAW_WORKSPACE:-…}`，有则用配置） |

**不要：**

- 在本目录对 `Agent/docker/...` 建 junction / 拷贝整树（那是把 Agent 嵌回 mailbus）
- 在已提交的 `docker-compose.yml` 写死 `../../Agent/docker/...`

**要：**

```bash
# docker-agents/.env（gitignore）
OPENCLAW_WORKSPACE=/mnt/e/path/to/your/openclaw_space
CODEX_WORKSPACE=/mnt/e/path/to/your/codex
```

路径可以指向本机任意位置（含你现在的 Agent 树）；那是**配置关联**，不是布局耦合。

可选脚本 `tools/ops/migrate_compose_workspaces.py` 仅当你**主动**想把数据镜像到仓内占位目录时使用；解耦不要求跑它。
