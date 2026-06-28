# L1 — Hermes Profile Framework Spec

> **Layer**: L1 · **Framework**: hermes_profile

## Agents

lingzhao, lingjin, lingxi, lingtuo, lingxun, lingzhang

## Runtime 契约

- Push: `docker exec hermes hermes chat --profile <profile> -q 'MSG' -Q --yolo`
- profile 名 = agent id；端口 9120–9127
- notice 可 auto_ack；task 须可验收

## 交付 SoT

见 [../../hermes/framework-runtime/references/delivery.md](../../hermes/framework-runtime/references/delivery.md)

## Sync

`mail/tools/sync-hermes-framework-skill.sh`
