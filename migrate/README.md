# Mailbus 目录迁移

把 mailbus 迁到新机器（Windows / Linux / WSL）时，**分别拷贝**下列目录，再用 CLI 写 `.env` 并重写路径。

## 要拷什么

见 [`manifest.yaml`](manifest.yaml)：

| 层级 | 变量 | 典型目录 |
|------|------|----------|
| 必拷 | `MAILBUS_ROOT` | `mail/` |
| 必拷 | `MAILBUS_DATA` | `mail/store/`（含 `run/` 若分离） |
| 可选 | `OPENCLAW_WORKSPACE` | `openclaw_space/` |
| 可选 | `OPENCODE_ROOT` | `opencode/` |
| 可选 | `NODE_MODULES` | `node_modules/` |
| 可选 | `HERMES_DATA` | `hermes-data/.hermes/` |

各 agent 工作区（如 `agent-f/`）按 manifest 的 `framework_workspaces` 或 `access/transport/*/transport.json` 的 `workspace` 字段。

## 快速用法

```bash
cd mail
pip install -e .

# 源机打包
mailbus migrate export --output /tmp/mailbus-bundle.tar.gz --prefix <OLD_MAILBUS_ROOT>

# 目标机解压 + 配置 + 人物加载
mailbus migrate import /tmp/mailbus-bundle.tar.gz --prefix /opt/mailbus

# 仅查看当前路径对照
mailbus migrate plan
```

## import 后自动执行

1. 写 `mail/.env`
2. `rewrite_paths` — 替换 store/transport 旧前缀
3. `init-store` + `sync-all-agent-layers` — 生成 config.json 与人物/skills
4. `mailbus compose sync` — 从 transport 生成 compose override 挂载
5. `mailbus doctor`

## 手动拷贝（不用 bundle）

1. 把整个 install 树拷到新前缀（保持相对路径）
2. `python migrate/write_env.py --prefix /new/root`
3. `python migrate/rewrite_paths.py --prefix /new/root`
4. `mailbus compose sync && mailbus doctor && mailbus start`

## 可选工具

- [`optional/cursor/`](optional/cursor/) — Cursor 数据迁 E 盘（与 mailbus 无关）

验收清单：[`verify/checklist.md`](verify/checklist.md)
