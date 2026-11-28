---
name: framework-runtime-hermes_profile
description: >
  Hermes Profile 框架边界（lingzhao/lingjin/lingxi 等）。--profile 隔离、notice 可 auto_ack。
  references 与 hermes 共用（../hermes/framework-runtime/references/）。
always: true
type: framework_skill
layer: L1
framework: hermes_profile
---

# Hermes Profile Framework Runtime

> type: `hermes_profile` · agents: lingzhao, lingjin, lingxi, lingtuo, lingxun, lingzhang

## Push 形态

```bash
docker exec hermes hermes chat --profile <profile> -q 'MSG' -Q --yolo
```

- 每 agent 独立 **profile**（通常 profile 名 = agent id）
- Dashboard 端口 9120–9127 与 profile 一一对应

## 10 条边界规则

1. 确认当前 **profile** 与 agent id 一致，勿串 profile
2. 开工前 memory search（见 [memory.md](../../hermes/framework-runtime/references/memory.md)）
3. 默认 flash；Pro 仅 mailbus 显式开启
4. 长文读 `msg-files`，CLI 只有路径
5. 方案/审计/巡检类交付写 msg-results 或 deliverables
6. notice 可 auto_ack；task 必须可验收
7. identities 只读：`/mailbus/identities/`
8. 编码类 task → 派 dali / lingyun / lingxiao，非 Hermes 长编码
9. 共享 mailbus 协议 → `mailbus-file-protocol`
10. 外部工具（Dify 等）走 `external-tools/adapters/`，非 Hermes CLI

## 参考文档（与 hermes 共用）

| 主题 | 文件 |
|------|------|
| Token | [../../hermes/framework-runtime/references/token.md](../../hermes/framework-runtime/references/token.md) |
| 能力 | [../../hermes/framework-runtime/references/capabilities.md](../../hermes/framework-runtime/references/capabilities.md) |
| 交付 | [../../hermes/framework-runtime/references/delivery.md](../../hermes/framework-runtime/references/delivery.md) |
| 记忆 | [../../hermes/framework-runtime/references/memory.md](../../hermes/framework-runtime/references/memory.md) |

## 自检

- [ ] profile 正确
- [ ] ack + msg-files
- [ ] msg-results / deliverable 路径
