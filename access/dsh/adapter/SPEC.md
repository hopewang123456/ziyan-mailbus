# L1 — DeepSeek Harness (dsh) Framework Spec

> **Layer**: L1 · **Framework**: dsh · **Agent**: lingtan

## Runtime 契约

- Push: `docker exec mailbus-dsh dsh --profile headless 'MSG'`
- 非交互单次 headless 执行；**永不 auto_ack**
- 常驻 web（实例控制台）仅容器内 `127.0.0.1:3080`（不映射宿主机；主链路 headless push）

## 交付 SoT

**D1 step-result**（与 production harness 同一套）— `store/msg-results/{task_id}/step-{step_id}.json`

- mailbus 复用 ack + D1 step-result 验收，不在 dsh 侧新造验收
- dsh 是 developer preview（API 会破），适配器**边界隔离**，业务代码不 import Cordis 内部包

## Sync

运行时数据路径由 mailbus 配置关联（`DSH_WORKSPACE` / `.env` / 设置页实例路径），
与 hermes / openclaw / codex 相同——**不**假设 `Agent/docker/dsh` 布局；
compose 未配置时回落 `docker-agents/workspaces/dsh` 空占位。profile 用 `--profile headless`。
