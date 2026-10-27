"""Metrics 域适配层（P2 B1-B3，2026-10-26）— 指标引擎（python 轻量自研路线）。

分层（规划文档 9.2）：
- manifest: 读 `shared/config/mailbus/metrics-manifest.json`（双栈唯一口径真源）
- collector: 按 manifest 口径现算 point 值（数据源=既有 store/应用服务）
- store: 时序追加 `store/metrics/timeseries.jsonl`（环形窗口，默认 7 天）
- query: 统一查询协议（metric + range + granularity，B2）

对外一律经 composition 门面（adapters 分包规则 #2）；无 Port——域服务型子包。
双栈差异化（D8/D5）：java 侧走 Micrometer/Actuator 路线，但消费同一份 manifest。
"""
