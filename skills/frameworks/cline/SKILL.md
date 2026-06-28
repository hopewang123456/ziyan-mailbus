---
name: framework-runtime-cline
description: >
  Cline 框架边界（LEGACY deprecated）。已迁移 Codex；仅保留 stub 供历史 config 参考。
always: true
type: framework_skill
layer: L1
framework: cline
status: deprecated
---

# Cline Framework Runtime（LEGACY）

> **status: deprecated** — 新任务请用 **codex**（lingxiao/lingjian）。  
> adapter: `ClineAdapter` · type: `cline`

## Push 形态（历史）

```bash
cline 'MSG' -P openai-compatible -m deepseek-chat -t 300 -c /mailbus/store --auto-approve true
```

- positional prompt，**无 auto_ack**
- 完成 SoT：`store/msg-results/{msg_id}.json`

## 边界（若仍被 push）

1. ack + msg-files + msg-results（同 codex）
2. 不要与新 Codex 容器混用同一 agent id
3. 迁移：改 `config.json` → `"type": "codex"`

## 参考

- 现行规范 → [`../codex/SKILL.md`](../codex/SKILL.md)
- 共享协议 → `mailbus-file-protocol`

## 自检

- [ ] 已确认是否应迁移到 codex
- [ ] msg-results 已写
