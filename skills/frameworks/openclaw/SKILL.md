---
name: framework-runtime-openclaw
description: >
  OpenClaw 框架边界（xiaoqi/yige）。openclaw agent 本地、notice 可 auto_ack、state_dir 隔离。
always: true
type: framework_skill
layer: L1
framework: openclaw
---

# OpenClaw Framework Runtime

> agents: **xiaoqi（小七）**, **yige（一哥）** · gateway :18789 / :18790

## Push 形态

```bash
openclaw agent --local --agent <id> --message 'MSG' --timeout 120
```

- 环境：`OPENCLAW_STATE_DIR` 按 agent 隔离（xiaoqi / yige）
- **notice** 可 auto_ack；调度/验收 task 须实质回复

## 10 条边界规则

1. ack → `store/inbox/{agent}/ack.json`
2. 读 `msg-files`；Kanban/task FSM 见 mailbus rules
3. 回复可走 mailbus API POST（非仅 chat）
4. **HEARTBEAT.md 保持短小**（省 token）
5. 不每轮重读 AGENTS.md（运行时已注入）
6. skills：`openclaw_space/skills/` 按需 Read
7. xiaoqi：拆单/验收；yige：内容运营，非 deep 编码
8. 编码派 dali/lingyun，方案派 lingzhao
9. 共享协议 → `mailbus-file-protocol`
10. 群聊礼仪：quality > quantity（见 AGENTS.md）

## 参考

| 主题 | 文件 |
|------|------|
| Token | [references/token.md](references/token.md) |
| 能力 | [references/capabilities.md](references/capabilities.md) |
| 交付 | [references/delivery.md](references/delivery.md) |
| 编码纪律 | [references/coding-discipline.md](references/coding-discipline.md) |

## 自检

- [ ] task 状态 FSM 正确
- [ ] 验收有依据（非空泛 OK）
