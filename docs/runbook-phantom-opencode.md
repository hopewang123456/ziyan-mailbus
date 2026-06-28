# Runbook — OpenCode phantom 完成 / Normalizer

## 症状

- inbox 标 done，但 pipeline FSM 不推进
- OpenCode 只写 `store/replies/` 或 `store/patches/`，无 `msg-results`

## 根因

FSM **仅**认 `store/msg-results/`。OpenCode 三源须经 Delivery Normalizer。

## 排查

1. 查 `store/msg-results/{msg_id}.json` 或 `store/msg-results/{task_id}/step-*.json`
2. 查 `store/replies/`、`store/patches/` 是否有对应 agent 输出
3. 跑 Normalizer 单测：`pytest tests/test_delivery_normalizer_opencode.py -v`
4. self_heal / pipeline_trigger 是否在 scan 中调用 normalizer（见 `lib/delivery_normalizer.py`）

## 配置 SoT

- `mail/config/frameworks/opencode/delivery.json`
- init-store 合并为 `framework_delivery.opencode`

## 修复动作

1. 手动补写 canonical `msg-results`（格式见 `mail/rules/common/task-fsm.md`）
2. Dashboard **继续** 同 step：`recover continue`
3. 连续 2 次 verify 失败 → 同工种 failover（`config/pipeline/role_failover.json`）

## E2E 验收（Phase 3.8）

真实 dali push 后须出现 msg-results；仅 reply 文本不得触发 done。
