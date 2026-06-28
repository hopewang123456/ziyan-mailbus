# ziyan-mailbus 测试计划

> **2026-06-25 更新**：`tests/test_*.py` 共 56 文件、432 用例。运行：`python -m pytest tests -q`  
> Windows 本机建议 `set PYTHONUTF8=1`；Docker/WSL 为 CI 推荐环境。

## 现有测试覆盖（摘要）

| 区域 | 文件 |
|------|------|
| Pipeline / FSM | test_pipeline_task.py, test_pipeline_trigger_p0.py, test_v2_regression.py, test_task_fsm.py |
| 推送 / 完成判定 | test_pusher*.py, test_file_task_push.py, test_task_completion.py |
| 扫描 / ack | test_scanner.py, test_ack_handler.py, test_archiver.py |
| Agent 适配 | test_agent_adapters.py, test_claude_launch.py, test_tier_dispatch.py |

## 仍偏弱的覆盖

- scheduler job runner 集成测
- lib/api/handlers_system 部分端点
- push_messages 真 CLI 端到端（有 mock 单测）

## 验收脚本

```bash
python tools/tools/ops/run-final-acceptance.py
python tools/check-preflight.py --data-dir store
bash docker-agents/mailbus-pipeline-e2e.sh
python tools/run-game-lvup-e2e.py --task-id game-lvup-TEST --data-dir store
```

## 历史 checklist（大部分已实现，保留作索引）

- tests/test_models.py — 数据模型
- tests/test_pusher.py — 推送逻辑
- tests/test_tracker.py — 任务追踪
- tests/test_heartbeat.py — 心跳检测
