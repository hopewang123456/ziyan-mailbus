# Pipeline v3 基础设施修复方案（2026-06-17）

> **原则**：只改 mailbus（compose / config / rules / identities / tools / scripts），**不改** Hermes、OpenClaw、Cline、OpenCode 源码；对 agent 零代码侵入，仅增加 Docker volume 挂载。

## 问题与修复对照

| # | 问题 | 修复（mailbus 侧） | 文件 |
|---|------|-------------------|------|
| 1 | Hermes 写 `/mailbus/store` 不落盘 | 各 agent 容器挂载 `store:/mailbus/store` rw | `docker-compose.yml` |
| 2 | 路径 `/mnt/e/...` 容器不可达 | config + identities 统一 `/mailbus/store` | `store/config.json`, `identities/*.md` |
| 3 | `bus send --type task` 重复 tracker | Step1 改 `POST /api/send-msg` + `pipeline-push-step1.py` | `tools/`, `submit-*-docker.sh` |
| 4 | Step1 无结构化工单 | `msg-files/*.md` 含 initiator/当前/下一步/summary | `tools/pipeline-push-step1.py` |
| 5 | phantom completion（replies 假完成） | 规则明确 + repair 清 phantom reply | `rules/pipeline-agent-paths.md` |
| 6 | stale queue / 重复 tracker | `repair-pipeline-stuck.py` | `tools/` |
| 7 | closed-loop 规则 agent 读不到 | 同步到 `store/rules/` | `store/rules/closed-loop-task-design.md` |

## 未改 mailbus lib/*.py 的刻意选择

~~以下逻辑仍在现有 `lib/` 中，通过 **运维脚本绕过** 而非改源码~~

**2026-06-17 更新**：已在 mailbus `lib/` 落地以下修复（仍不改 agent 源码）：

| 问题 | lib 修复 |
|------|----------|
| `cmd_send` 误建 tracker | `pipeline_task.should_create_tracker_for_send` + `commands.py` |
| pusher 无 post-CLI 验收 | `pusher._save_reply` → `verify_pipeline_step_delivery` |
| stale_processing 2min 空转 | `scanner.recover_inbox_stale_states` 用 `pipeline_ops` cooldown |
| stale queue | `scanner._cleanup_stale_queue_files` |
| inbox 过早 done | `self_heal.sync_tracker_and_inbox` 校验 step/agent |
| Step1 无工单 | `pipeline_work_order.py` + `pipeline_trigger._send_task` |
| msg-* 重复 tracker | `self_heal.normalize_legacy_tracker_audit_flags` |

运维脚本（`tools/`、`docker-agents/`）与 lib 互补，仍保留。

## 验证阶梯（v3 前必跑）

| 层级 | 脚本 | 验证什么 | 耗时 |
|------|------|----------|------|
| L0 | `verify-agent-store-mount.sh` | 容器 shell 写 store | ~10s |
| **L1** | **`smoke-agent-write.sh`** | **agent 经 mailbus 真实落盘** | **~1–7min** |
| L2 | `smoke-pipeline-mini.sh` | 2 步 pipeline + trigger 推进 | ~10–20min |
| L3 | `pre-v3-readiness.sh` | 环境 + 单测 + monitor | ~2min（不含 L1） |
| L4 | `run-v3-autovalidation.py --submit` | 12 步 LIVE 全链 | 数小时 |

```bash
# 最短落盘（已通过 2026-06-17）
bash docker-agents/smoke-agent-write.sh lingzhao

# mini pipeline gate
bash docker-agents/smoke-pipeline-mini.sh

# 全链 v3
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/run-v3-autovalidation.py --submit
```

```bash
# WSL 内
cd /mnt/e/ai_tools/mail/docker-agents
bash apply-pipeline-infra-fix.sh

# 验证挂载
bash verify-agent-store-mount.sh

# 修复 v3 并重推 Step1（不自动重跑验收，按需执行）
docker exec docker-agents-mailbus-1 bash /mailbus/docker-agents/submit-game-stellar-v3-live-docker.sh
```

## 工单字段（Step1 msg-files）

| 字段 | 来源 |
|------|------|
| 发起人 | mailbus |
| 当前执行人 | `--agent` / chain[0].to_person |
| 下一步执行人 | planned_agents[0] |
| task_id | pipeline task |
| 状态 | running |
| summary | task.summary |

Step2+ 仍由现有 `pipeline_trigger._send_task` 自动生成（无需改 lib）。

## 验收标准

1. `verify-agent-store-mount.sh` 全部 OK
2. 灵昭执行后 **磁盘存在** `store/msg-results/game-stellar-20260618.json`
3. cron 出现 `[pipeline] lingzhao 完成 ->` 并推 lingxi
4. 无 `msg-*` 重复 running tracker
