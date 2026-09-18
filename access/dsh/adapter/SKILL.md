---
type: framework_skill
framework: dsh
layer: L1
---

# dsh runtime skill

DeepSeek Harness（dsh）L1：`docker exec mailbus-dsh dsh --profile headless 'MSG'`。

- 非交互单次 headless；**永不 auto_ack**
- 交付 SoT：D1 `store/msg-results/{task_id}/step-{step_id}.json`
- 工作区由 `DSH_WORKSPACE` / 设置页 `install_path` 配置关联；compose 未设 env 时回落 `docker-agents/workspaces/dsh`
- 详见同目录 `SPEC.md`
