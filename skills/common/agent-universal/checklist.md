# L0 — 通用自检

每次 mailbus 任务结束前的 checkpoint：

- [ ] 已写 `store/inbox/{agent}/ack.json`
- [ ] 已读 `store/msg-files/{msg_id}.md`（若存在）
- [ ] 已写 **L1 框架规定的交付 SoT**（见 `framework-runtime-*/references/delivery.md`）
- [ ] summary ≤200 字；长输出在 patch / details / md
- [ ] 未越权做其他工种 L2 边界内工作
- [ ] 未违反 `store/rules/team-secrets-policy.md`

框架与工种附加项 → 各层 `checklist.md` 或 SKILL.md 自检节。
