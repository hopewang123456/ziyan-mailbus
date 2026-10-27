# Runbook — bus serve 热加载与 inbox 减负

> 2026-07-17 · 配合 [`../2026-07-17-mailbus-next-optimization.md`](../2026-07-17-mailbus-next-optimization.md)

## bus serve 何时必须重启

`bus serve` / 内嵌 scheduler **不会**自动热加载 Python 代码与多数内存态配置。

| 变更类型 | 是否必须重启 serve | 说明 |
|----------|-------------------|------|
| `lib/**/*.py` 代码 | **是** | 进程已 import 的模块不刷新 |
| `store/config.json` 部分字段（agents/models/smart_routing） | **建议重启** | 部分读盘路径可即时生效，但 push/scan 长驻态易脏读 |
| `config/llm/ollama.json` 种子 | 下次 `init --merge` + **重启** | 仅改种子不改 store 无效 |
| inbox / tasks 文件 | 否 | 每轮 scan 读盘 |
| skills/rules（vault 挂载） | 否（agent 侧） | 容器只读挂载；agent CLI 下次会话读到新文件 |

**操作：**

```powershell
# 停掉当前 serve 后重启（按你方常驻方式二选一）
python -m bus serve
# 或 docker compose 中的 mailbus 服务
```

改完 Internal LLM / smart_routing 后，用：

```powershell
python tools/ops/setup-internal-llm.py --data-dir store --json
```

确认 `ready: true` 再发任务。

## inbox 减负策略（轻量）

1. **notice / rule-change / offline**：应带 `action.no_llm: true`，避免占 urgent 与 CLI token  
2. **历史积压**：优先归档已 `done` / 过期 welcome；对长期 `pending` 且 `pushed_count=0` 的 offline notice 人工 `mark-read` 或清理  
3. **工具**：

```powershell
python tools/mailbus-store-cleanup.py --data-dir store --dry-run
# 确认后再去掉 --dry-run
```

4. **监控**：`pending` 且 `pushed_count=0` 超过 N 分钟 → 查 scan 日志与 agent 存活，而不是连发新 task

## 小任务回归（冒烟）

```powershell
# 1) 总线健康
python -m bus status
# 2) 发一条 urgent task（示例：灵云）
python -m bus send lingyun --type task --priority urgent --from mailbus --msg "REGRESSION: ping only. Reply ACK in one line. no code changes."
# 3) 触发一轮推送
python -m bus scan
# 4) 看 inbox / replies / msg-results
python -m bus status --agent lingyun
```

多 agent 串联请用 pipeline / tracker，不要对全员 `broadcast` task（易打爆 token）。
