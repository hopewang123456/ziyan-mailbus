# 告警系统完善方案

## 当前状态
- 只有 2 条告警记录（5月24日的inbox积压）
- 没有告警解除机制
- 没有区分活跃/已解除状态

## 告警数据结构（改动 alert.json）

```json
{
  "id": "alert-<timestamp>",
  "type": "inbox_overflow | agent_offline | task_timeout | pipeline_loop | chat_q_timeout | result_file_missing | push_failed",
  "severity": "critical | warn | info",
  "agent": "agent_name | null",
  "message": "告警描述",
  "status": "active | resolved | acknowledged | expired",
  "resolved_at": "解除时间 | null",
  "resolved_by": "auto | agent_name",
  "created_at": "创建时间",
  "assignee": "处理人"
}
```

## 告警类型 + 触发 + 解除

| 类型 | 严重级别 | 触发条件 | 解除条件 |
|------|---------|---------|---------|
| inbox_overflow | warn | inbox 消息 > 50 条 | inbox 消息降到 < 30 条 |
| agent_offline | critical | 心跳连续 3 次未响应 | 心跳恢复 |
| task_timeout | warn | pipeline 步骤超时 15 分钟 | 步骤推进到下一步 |
| pipeline_loop | warn | 自循环检测触发 | 同任务 10 分钟无新自循环 |
| chat_q_timeout | warn | 连续 3 次 chat -q 超时 | 后续 3 次都成功 |
| result_file_missing | info | 文件模式 30 分钟未写结果文件 | 结果文件已写入 |
| push_failed | critical | CLI 推送连续 3 次失败 | 下次推送成功 |

## 实现位置
- 告警写入：`lib/alerter.py` 现有的 `alert()` 函数增强
- 告警解除：`lib/scanner.py` 的 `run_housekeeping` 中新增 `_resolve_alerts()`
- 告警查询：现有 `/api/alerts` 增加 `?status=active` 过滤
- Dashboard 展示：按活跃/已解除分组

## 告警去重规则
- 同类型 + 同 agent + 同严重级别的告警，15 分钟内不重复生成
- 已存在的 active 告警，不重复创建
- 示例：inbox_overflow 每 15 分钟检查一次是否还在 50 条以上

## 告警通知方式
| 严重级别 | 通知方式 |
|---------|---------|
| critical | 写入 alerts + 即时推送 pusher 给 assignee |
| warn | 只写入 alerts，不推送 |
| info | 只记录，仅 Dashboard 展示 |

## Dashboard 操作
每条告警右侧加三个按钮：
- ✅ 已确认 → status = acknowledged
- ✅ 已处理 → status = resolved
- ❌ 忽略 → status = expired

## 告警保留时间
- resolved/expired 状态的告警 7 天后自动归档删除
- active 状态的告警不自动删除

## 管道联动
所有告警统一通过 `alerter.py` 的 `alert()` 函数写入，不分散到各模块。
pipeline 检测到的异常（自循环、超时等）也调用 `alert()` 写入。

## 告警解除检测逻辑（run_housekeeping 中）

```python
def _resolve_alerts(data_dir):
    alerts_file = os.path.join(data_dir, "alerts.json")
    if not os.path.exists(alerts_file):
        return
    alerts = json_read(alerts_file, {"alerts": []})
    changed = False
    for alert in alerts.get("alerts", []):
        if alert.get("status") != "active":
            continue
        # 各类型解除检测
        if alert["type"] == "inbox_overflow":
            # 检查 inbox 是否已降到 30 条以下
            ...
        elif alert["type"] == "agent_offline":
            # 检查心跳是否已恢复
            ...
        elif alert["type"] == "task_timeout":
            # 检查 pipeline 步骤是否已推进
            ...
        if resolved:
            alert["status"] = "resolved"
            alert["resolved_at"] = _now_iso()
            alert["resolved_by"] = "auto"
            changed = True
    if changed:
        json_write(alerts_file, alerts)
```

## Dashboard 改动
- 告警 tab 分三组：🔴 活跃告警 / 🟢 已解除 / ⚪ 已过期
- 每条告警显示类型图标、严重级别徽章、时间、处理人
- 点击告警可手动标记为 acknowledged

## 优先级
P1 — 建议下周开始实施
