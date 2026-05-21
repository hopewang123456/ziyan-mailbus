# ziyan-mailbus

多 Agent 消息总线系统 — 独立、解耦、轻量的文件级消息中间件。

## 设计哲学

- **文件即通信**：消息存 JSON 文件，零中间件依赖
- **双向确认**：CLI 推送 + agent 主动 ack，不搞"推送即送达"的幻觉
- **先队列再推送**：加急排队优先，普通排队顺序，同发件人批量推送
- **故障隔离**：推送失败 3 次 → 写错误日志 → 监控 agent 扫日志找修复方案

## 快速开始

```bash
# 安装
pip install -e .

# 启动总线 cron（每分钟扫描全员 inbox）
crontab -e
# 添加：* * * * * cd /path/to/ziyan-mailbus && python -m mailbus scan

# 手动操作
python -m mailbus scan                     # 扫描全员的 inbox 并推送
python -m mailbus send lingxiao --msg "..." # 发消息给指定 agent
python -m mailbus ack --msg-id msg-xxx     # agent 确认收到
python -m mailbus status                   # 查看消息状态
python -m mailbus retry                    # 重试失败消息
```

## 协议

MIT
