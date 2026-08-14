# L1 — Hermes Profile Framework Spec

> **Layer**: L1 · **Framework**: hermes_profile

## Agents

agent-a, agent-b, agent-c, agent-d, agent-e, agent-f

## Runtime 契约

- Push: `docker exec hermes hermes chat --profile <profile> -q 'MSG' -Q --yolo`
- profile 名 = agent id；端口 9120–9127
- notice 可 auto_ack；task 须可验收

## 交付 SoT

见 [../../hermes/framework-runtime/references/delivery.md](../../hermes/framework-runtime/references/delivery.md)

## Sync

`mail/tools/sync-all-agent-layers.py`（L0–L2 层 skill 同步，Vault SoT + 运行时 junction）
