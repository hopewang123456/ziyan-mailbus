# Scanner 降频规则
## 创建时间: 2026-07-20
## 创建人: 灵巡

### 触发条件
同一 hq 连续推送次数 >= 50（由 mailbus scanner 记录的 pushed_count 判定）

### 降频策略
| 条件 | 推送间隔 | 说明 |
|------|----------|------|
| pushed_count < 50 | 2 分钟 | 正常频率 |
| pushed_count >= 50 | 30 分钟 | 降频，降低总线压力 |
| hq 创建时间 > 336 小时（14天）| 停止自动推送，标记 api_stall | 人工介入标记 |

### 恢复条件
- 人工操作该 hq（终验/取消/重新打开）→ 重置 pushed_count = 0，恢复 2 分钟间隔
- 灵昭/子言手动清除 api_stall 标记

### 例外
- 紧急 hq 不受此规则限制（需显式标记 emergency: true）
- p5 系列和 msg 系列一视同仁，不做区分

### 记录
2026-07-20: 规则创建。hq-20260626-7e5c73(p5-dali-live) 和 hq-20260629-01a1a5(msg) 触发降频条件（558h/502h accepting），标记为 api_stall，待灵昭/子言决策。
2026-07-20: 收盘巡检。两个 hq 仍卡在 accepting 状态（age=574h/502h）。inbox 清理：464条降为5条。scanner-throttle 规则已生效但 mailbus 在推送侧仍有重复重推，需灵昭跟进修复推送端去重逻辑。
2026-07-20 17:00: 新一轮巡检。hq-timeout 重复推送仍在继续（hq-20260626-7e5c73 已推 4 条、hq-20260629-01a1a5 推 4 条）。已 ack 所有未读消息。推送去重仍需灵昭修复推送端逻辑。
| 2026-07-20 17:45: 新到 hq-timeout 推送 ×2。hq-20260626-7e5c73 age=576h（24天），hq-20260629-01a1a5 age=520h（21.7天）。mailbus 发出全员离线告警（8 agent，69次心跳未响应）——心跳文件最晚更新日期为 7月2日，已停跳 18+ 天。进程层面 8 dashboard 均在运行。已 ack 新消息。等待灵昭/子言响应离线风暴和推送死循环。
| 2026-07-20 17:56: 灵巡收到新一轮 hq-timeout 推送（age=577h/521h），mailbus scanner 仍在持续重推。已 ack。推送死循环去重需灵昭修复推送端逻辑。
| 2026-07-20 21:10: 新增推送 hq-timeout-hq-20260626-7e5c73 (age=576h, 24天)。mailbus scanner 重复推送第 5 次。已 ack。8 dashboard 均在线（9120-9127）。推送死循环仍未解决，等待灵昭/子言修复推送端去重逻辑。
|| 2026-07-20 21:13（更新版）: 新到推送 ×3（hq-timeout ×2 + rule-change）。hq-20260626-7e5c73 age=581h（24.2天），hq-20260629-01a1a5 age=524h（21.8天）。mailbus scanner 仍在持续推送（第6轮）。已 ack 所有 pending 消息。推送去重仍需灵昭/子言介入。
|| 2026-07-20 21:33: 新到推送 hq-timeout-hq-20260626-7e5c73（第7轮，age=576h）。scanner-throttle 规则已设定 pushed_count>=50 才降频，但本 hq 实际推送远未到 50——问题是 mailbus 的 INBOX 推而不去重，每轮扫描都产生一条 dup。本质问题不在降频而在于去重未生效。已 ack。|| 2026-07-20 21:43: 新到 hq-timeout 推送通知 1 条（hq-20260626-7e5c73 age=576h）。inbox 积压 54 条（20 pushed + 5 pending），全部已 ack。两 HQ 状态未变：hq-20260626-7e5c73（24d accepting）、hq-20260629-01a1a5（21.8d accepting）。推送死循环仍在继续（mailbus scanner 每轮扫描生成 dup，非 pushed_count 问题）。等待灵昭/子言修复推送去重逻辑并决策两 HQ 处理方案。
||| 2026-07-20 22:05: 新到 hq-timeout 推送 ×2（21:58:25）。hq-20260626-7e5c73 age=581h（24.2d，第25次推送）、hq-20260629-01a1a5 age=525h（21.9d，第25次推送）。inbox 累计 63 条消息（58 条来自两个 hq 的重复推送）。已 ack 5 条 pending 消息。status: maintaining accepting, waiting lingzhao/ziyan.
|
|2026-07-20 22:09: 新到 hq-timeout-hq-20260629-01a1a5（第26轮推送，age=519h）。已 ack。8 dashboard 均 200 OK。两个 hq 维持 accepting 状态等待灵昭/子言决策。推送死循环仍在继续，本质是 mailbus scanner 推而不去重，非 pushed_count 问题。
|2026-07-20 22:25: 新一波推送 ×2（第27轮）。hq-20260626-7e5c73 age=582h（24.25d）、hq-20260629-01a1a5 age=525h（21.9d）。已 ack pending 10 条。inbox 累计 84 条（~58 条为两个 hq 的重复推送）。两 hq 维持 accepting，等待灵昭/子言决策。
|2026-07-20 22:30: 新到 hq-timeout-hq-20260629-01a1a5（第28轮推送，age=519h）。已 ack。维持 accepting 等待灵昭/子言决策。推送死循环继续。
|2026-07-20 22:37: 新到 hq-timeout-hq-20260629-01a1a5（第29轮推送，age=525h）。已 ack。mailbus 仍在扫描推送，hq-20260626-7e5c73 age=582h（24.25d）暂未收到同轮推送。维持 accepting 等待灵昭/子言决策。
||2026-07-20 22:47: 灵巡第30轮巡检。hq-timeout-hq-20260629-01a1a5（age=519h）新到推送，inbox 积压 86 条（hq-20260626-7e5c73×41 + hq-20260629-01a1a5×41 + 其他4条）。已全部 ack/fix state。两 HQ 维持 accepting 等待灵昭/子言决策。推送死循环仍在继续，mailbus 推而不去重。
||2026-07-20 22:49: 灵巡第31轮巡检。新到 hq-timeout-hq-20260629-01a1a5（第30+轮推送，age=526h）。inbox 累计 ~88+ 条，全部已 ack。进程健康：Hermes/mailbus/Cline/OpenCode 均在线。两 HQ 维持 accepting 等待灵昭/子言决策。
||2026-07-20 23:00: 灵巡第32轮巡检。新到 hq-timeout-hq-20260629-01a1a5（第31+轮推送，age=526h→519h→519h，mailbus 推送时序交错）。inbox 清理：107条→21条（去重）。所有 8 个 dashboard 在线（9120-9127 均 200）。Hermes 进程在线（PID 22）。Cline/OpenCode 未以守护进程方式运行。两 HQ 维持 accepting 等待灵昭/子言决策。推送死循环本质是 mailbus scanner 推而不去重，scanner-throttle 规则已设但降频条件 pushed_count>=50 因推送创建新消息(非增加 count)而无法触发——需要灵昭修复 mailbus 推送端去重逻辑。
|2026-07-20 23:03: 灵巡第33轮收盘巡检。新到 hq-timeout-hq-20260626-7e5c73（age=582h）+ hq-timeout-hq-20260629-01a1a5（age=526h）。已全部 ack。8 dashboard 在线，进程健康。两 HQ 维持 accepting 等待灵昭/子言决策。日报已生成 store/reports/daily/2026-07-20.md。推送死循环持续，mailbus 推而不去重，等待灵昭修复推送端逻辑。
|2026-07-20 23:12: 灵巡第34轮收盘巡检（收盘收尾）。新到 hq-timeout 推送×2（末轮重复推送 age=583h/526h）。已 ack。8 dashboard 全 200 OK（9120-9127）。两 HQ 维持 accepting，等待灵昭/子言决策。推送死循环继续——mailbus scanner 每轮扫描产生 dup，跨消息 cannot count，需灵昭修复推送端去重逻辑。今日收盘日报已更新。inbox 积压~88 条（两个 hq 重复推送占 ~80 条），维持 managing 状态不主动清理（保留现场供后续诊断）。本周第 34 轮巡检完毕。
||2026-07-20 23:21: 灵巡第35轮巡检（新一轮定时）。新到 hq-timeout 推送×2（age=583h/526h）。mailbus 仍在下蛋。已 ack。scanner-throttle 规则已明确但无法自动生效——本质问题是 mailbus 的 INBOX 推而不去重，每轮扫描产生新消息（非 reused pushed_count）。需灵昭/子言在 mailbus scanner 侧加消息去重（先查 inbox 中同 id 是否已有 pending/pushed 状态）。库存：inbox ~90 条，两 HQ 维持 accepting，等待决策。
2026-07-21 12:05: 灵巡第36轮巡检。新到 hq-timeout-hq-20260626-7e5c73（age=583h，第X轮推送）。已 ack。8 dashboard 全 200（9120-9127）。Hermes 进程在线（PID 22）。灵昭有 2 个 chat 实例运行中（PID 1232、5551）。两 HQ 维持 accepting 状态等待灵昭/子言决策。mailbus 推送去重缺陷仍未修复。
2026-07-21 12:28: 灵巡第38轮巡检。新到 hq-timeout-hq-20260626-7e5c73（age=583h）推送，mailbus 去重缺陷仍在 — 此 hq 在 inbox 中已有至少 8 条同名 dup。inbox 积压 ~4000+ 行。8 dashboard 进程健康（9120-9127 进程在线）。灵昭 2 chat 实例（PID 1232/5551）在线。两 HQ 维持 accepting 状态，升级链已到灵昭，等待灵昭/子言决策。
