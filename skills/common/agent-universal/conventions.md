# L0 — 通用规范

## 路径

| 视角 | store 根 | inbox |
|------|----------|-------|
| 容器内 | `/mailbus/store` | `/mailbus/store/inbox/{agent}/` |
| 宿主机 WSL | `/mnt/e/ai_tools/mail/store` | 同上相对路径 |
| Windows | `E:\ai_tools\mail\store` | 同上 |

- msg-files: `store/msg-files/{msg_id}.md`
- msg-results: `store/msg-results/{msg_id}.json`（L1 规定是否 mandatory）
- patches: `store/patches/`
- replies: `store/replies/{sender}.json`

## 时间戳

- ISO 8601，带时区：`2026-06-24T12:00:00+08:00` 或 `...Z`

## 文本上限

| 字段 | 上限 |
|------|------|
| push CLI 正文 | 600 字（见 push-discipline） |
| summary | 200 字 |
| pipeline 每步 summary | 200 字 |

## Spec 包结构（L0–L2 统一）

```
{package}/
├── SPEC.md
├── boundaries.md
├── conventions.md
├── checklist.md
├── SKILL.md          # ≤120 行路由
└── references/
```

## 组合顺序（skills-index）

1. L0: `agent-universal`, `mailbus-file-protocol`
2. L1: `framework-runtime-{framework}`
3. L2: `role-{archetype}`, `role-overlay-{agent_id}`
4. L3: domain skills（按需）
