# L0 — Agent Universal Spec

> **Layer**: L0 · **Scope**: 所有子言·AI 团队 agent（不论框架与工种）  
> **SoT 路径**: `mail/adapters/_shared/agent-universal/`  
> **运行时镜像**: `store/rules/agent-layer-spec.md`（L0 节）

## Purpose

定义每个 agent 必须遵守的**不变量**：红线、通信契约、路径规范、完成举证要求。不包含框架 push 形态（L1）或工种职责（L2）。

## Invariants

1. **Phantom 完成禁止** — 聊天式「已完成」不算交付；必须落盘框架规定的 SoT（见 L1 `references/delivery.md`）。
2. **Ack 必写** — 收到 mailbus push 后第一时间写 `store/inbox/{agent}/ack.json`。
3. **工单必读** — 存在 `store/msg-files/{msg_id}.md` 时，执行前完整阅读。
4. **Summary 上限** — 回执 summary ≤200 字；细节放 patch / details / 独立 md。
5. **跨 agent 禁越权** — 不替其他工种做其 L2 边界内的工作（见 `mail/roles/archetypes/`）。
6. **团队规则服从** — `store/rules/` 下 secrets、execution-order、iteration-protocol 等（指针见 `references/team-rules.md`）。

## Acceptance

- [ ] 任意 agent 的合规集 = L0 + L1 + L2 archetype + L2 overlay + identity + 按需 L3 domain skills
- [ ] identity / AGENTS.md 不含 inline mailbus 交付表（由 L0/L1 skill 承担）
- [ ] `validate-agent-layers.py --check` 通过

## References

| 文档 | 内容 |
|------|------|
| [boundaries.md](boundaries.md) | 红线与听命链 |
| [conventions.md](conventions.md) | 路径、时间戳、命名 |
| [checklist.md](checklist.md) | 通用自检 |
| [SKILL.md](SKILL.md) | 路由 skill（≤120 行） |
