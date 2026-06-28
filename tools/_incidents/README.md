# postmortem / 一次性修复脚本

> Phase 6 · P6-C01 — 无 runtime/cron/scheduler 引用；保留供 game-courier 等事故复盘对照。

勿从 `docker-agents/start-team.sh` 或 scan 路径调用。需要复跑时显式指定路径：

```bash
python mail/tools/_incidents/patch-courier-interactive.py
```
