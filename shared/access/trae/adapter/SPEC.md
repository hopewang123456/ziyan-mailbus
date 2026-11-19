# L1 — Trae Framework Spec

> **Layer**: L1 · **Framework**: trae · **接入方式**: MCP（拉模式）

## Runtime 契约

- 接入：MCP server（mailbus 自带），Trae 侧配为 MCP client
  - stdio：`mailbus mcp --agent {agent}`（推荐，Trae 以子进程拉起）
  - http：`mailbus mcp --agent {agent} --transport http --port 9816` → `http://127.0.0.1:9816/mcp`
  - java 栈：`java -jar mailbus-boot.jar --spring.profiles.active=mcp`（环境变量 `MAILBUS_AGENT`）
- **无 push CLI**：`allow_no_push_cli=True`。总线无法主动推送到 Trae，投递靠 Trae 调用 `mailbus_inbox`
- **无 auto_ack** · 完成 SoT：**msg-results**
- 角色（dispatcher / executor / reviewer）由 store 里 agent 卡配置决定，不由接入方式决定

## 拉模式补偿

| 场景 | 做法 |
|---|---|
| 会话开始 | 先调 `mailbus_inbox` 读收件箱 |
| 等任务 | `mailbus_wait`（长轮询，≤60s），避免空转 |
| 工单完成 | `mailbus_step_result` 提交回执（落 msg-results） |
| 发令 | `mailbus_command_draft` 预演 → `mailbus_task_create` 正式创建 |

## 工具面

唯一 SoT：`shared/contracts/mcp-tools-v0.json`（15 个默认工具 + 1 个管理工具）。
双栈工具面一致性由 `tools/mcp_surface_diff.py` 对拍钉死。

## 交付 SoT（exclusive）

`store/msg-results/{msg_id}.json`

## 排障

- 工具未出现：确认 `--agent` 已在总线注册（`mailbus agent-add <name> --type trae`）
- 管理工具缺失：默认不注册，需 `--enable-admin`（细粒度授权在 D20）
- stdio 无响应：客户端 stdout 被日志污染时检查 server 启动参数（java 侧已用 `logging.level.root=OFF`）
