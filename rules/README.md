# ⚠️ 已弃用 — 请使用 store/rules/

运行时唯一真相源：**`store/rules/`**（容器内 `/mailbus/store/rules/`）。

**Agent 分层 spec（2026-06-24）** → `store/rules/agent-layer-spec.md`  
**Adapter 层说明** → `store/rules/agent-adapter-layer.md`

本目录仅保留历史镜像，**请勿在此修改**。团队规范修改后执行：

```bash
python3 tools/sync-team-rules.py --data-dir store
python3 tools/sync-all-agent-layers.py
```

FSM 规范见：`store/rules/task-fsm.md`
