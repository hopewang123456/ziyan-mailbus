---
name: framework-runtime-codex
description: >
  Codex CLI 框架边界（lingxiao/lingjian）。codex exec  ephemeral、msg-results 为完成 SoT。
always: true
type: framework_skill
layer: L1
framework: codex
---

# Codex Framework Runtime

> agents: **lingxiao**, **lingjian** · `CODEX_HOME/skills`

## Push 形态

```bash
codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c 'approval_policy="never"' -m deepseek-v4-flash 'MSG'
```

- **无 auto_ack**；**无跨 push 会话**（`--ephemeral`）
- 完成 SoT：`store/msg-results/{msg_id}.json`

## 10 条边界规则

1. ack → `store/inbox/{agent}/ack.json`
2. 读 `msg-files` 再执行
3. 必须写 **msg-results**（无文件 = 未完成）
4. skills 按需 Read，先读 `lingxiao-skills-index` 路由
5. lingxiao：架构/ADR/GitHub；lingjian：审查 reasoner 档
6. 默认 flash；reasoner 仅 lingjian 审查场景
7. cwd：`/mailbus/store` 或 agent workspace
8. 不写业务 E2E 测试代码 → 派 lingyan
9. 共享协议 → `mailbus-file-protocol`
10. sync 刷新 skills：`sync-codex-agent-skills.sh`

## 参考

| 主题 | 文件 |
|------|------|
| Token | [references/token.md](references/token.md) |
| 能力 | [references/capabilities.md](references/capabilities.md) |
| 交付 | [references/delivery.md](references/delivery.md) |

## 自检

- [ ] msg-results 存在且 status 正确
- [ ] summary ≤200 字
