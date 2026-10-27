# mailbus-ports — 端口层与 Python 镜像对照（R6）

端口层（hexagonal ports）。本包是 **java ↔ python 双轨互为镜像的锚点**：python 侧对应
`python/lib/interfaces/`（Protocol 定义），两侧同名端口保持**语义对齐**（方法签名语言习惯
各异，但职责与调用契约一致）。

## 对照表（2026-10-26 基线，P0a 建立）

| 域 | Python `lib/interfaces/` | Java `mailbus-ports` | 状态 |
|----|--------------------------|----------------------|------|
| 消息存储 | *(store 内联，未提 Port)* | `MessageRepository` | java 先行，python 侧 M2 回填对照 |
| 消息归档 | *(同上)* | `MessageArchiver` | 同上 |
| 事件日志 | *(同上)* | `MessageEventLog` | 同上 |
| 通知 | `orchestration.NotifierPort` | `Notifier` | **已镜像**（语义对齐；python 的 per-channel 隔离经验已注入 java javadoc） |
| Agent 目录 | *(agent_registry adapter 内联)* | `AgentDirectory` | java 先行 |
| Agent 卡导入 | *(a2a.agent_card_cache 内联)* | `AgentCardImporter` | java 先行，M2 与 A2A transport 汇合 |
| 存储迁移 | *(StoreMigrator 在 python 为脚本)* | `StoreMigrator` | java 先行 |
| 人机闸门 | `gates.HumanGatePort` + `AuditPort` | — | M2 补（P1 发令窗口依赖） |
| 工单 FSM | `orchestration.TaskFsmPort` | — | M2 补 |
| 编排 | `orchestration.OrchestrationPort` + `BudgetMeterPort` | — | M2-M3 补 |
| 消息传输 | `message_transport.MessageTransportPort` | — | M2 补（A2A 官方 SDK 之上，AA1） |
| A2A 传输 | `message_transport.A2ATransportPort` + `BridgedAgentPort` | — | M2-M3 补 |
| 结果存储 | `results.ResultStorePort` | — | M2 补 |
| 集成 | `integrations.IntegrationsPort` | — | M3 补 |
| 运行时 | `runtime.AgentRuntimePort` | — | M3 补 |
| 运维 | `ops.OpsPort` | — | M3 补 |
| 平面(宿主/容器) | `plane.HostPlanePort` + `ContainerPlanePort` | — | M3 补 |
| 本地化 | `locale.LocalePort` | — | 按需 |
| 认证 | `auth.AuthPort` | — | M2 补（P1 子言身份相关） |

## 规则

1. 新增端口必须在本表登记（python 对应物或「java 先行」标注）。
2. 端口禁止依赖 Spring（`domainHasZeroSpringDependencies` 同样精神；组合根装配是 boot 的事，L3）。
3. python 侧毛刺备忘：`_PathPort` 错位在 `adapters/runtime/paths.py`，P0b R1/R3 时归位 interfaces——java 侧不要复制该错位。
