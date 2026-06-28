# ⚠️ 已弃用 — mailbus 消息处理标准化流程

> **2026-06-24 起** 团队 agent 边界由 **L0–L3 分层 spec** 统一定义，本文件不再作为边界 SoT。

## 现行规范（请读这些）

| 层级 | 路径 |
|------|------|
| Meta | [`docs/agent-layer-spec.md`](docs/agent-layer-spec.md) · `store/rules/agent-layer-spec.md` |
| L0 | `mail/adapters/_shared/agent-universal/` · `mailbus-file-protocol/` |
| L1 | `mail/adapters/{framework}/framework-runtime/` |
| L2 | `mail/roles/archetypes/` · `mail/roles/overlays/{agent}/` |

校验：`python mail/tools/validate-agent-layers.py --check`  
Sync：`python mail/tools/patch-skills-index-framework.py`

---

## 以下内容为历史镜像（勿在新工单中引用）

<details>
<summary>展开旧版三步流程（已迁移至 L0/L1 skills）</summary>

### 第 1 步：写 ACK

```json
{"action":"ack","msg_id":"<消息ID>","agent":"<你的key>","timestamp":"<ISO时间>"}
```

路径：`store/inbox/{agent}/ack.json`

### 第 2 步：执行任务

先读 `store/msg-files/{msg_id}.md`（若存在）。

### 第 3 步：交付

**按框架 L1 SoT**，不再统一用 API 聊天回执：
- codex / claude_code → `store/msg-results/{msg_id}.json`
- opencode (dali) → patch + `store/replies/{sender}.json`
- openclaw / hermes → 实质回复或约定落盘

API 发信（可选通知，非所有框架的 pipeline SoT）：

```bash
curl -X POST http://localhost:9814/api/send-msg \
  -H "Content-Type: application/json" \
  -d '{"from":"<agent>","to":"<to>","type":"reply","content":"..."}'
```

</details>
