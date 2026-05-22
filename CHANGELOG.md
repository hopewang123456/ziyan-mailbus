# Changelog

## 1.0.0 (2026-05-22)

### 特性
- **消息总线核心**：文件级 JSON 消息系统，零中间件依赖
- **CLI 推送**：通过 Agent 的 CLI 命令推送消息，支持 30 秒超时 + 3 次重试
- **双向 ack 确认**：Agent 写 ack.json 回复总线，状态流转 `pending → pushed → acknowledged → archived`
- **优先级队列**：加急消息（urgent）优先推送，普通消息排队
- **Agent 类型抽象**：统一 `agent_types` 配置模板，已内置 6 种框架支持
  - `hermes` / `hermes_profile` / `openclaw` / `cline` / `opencode` / `none`
- **公告板**：`broadcast` 命令一键推送全员
- **错误日志**：JSONL 格式按周分文件，自动清理 30 天前的日志
- **归档策略**：已 ack 消息 7 天 / 300 条自动归档
- **Agent 管理**：`agent-add` / `agent-remove` 注册和移除 Agent

### 集成
- **AgentMemory 桥接**：`mailbus-memory-bridge.py` 自动将已 ack 消息同步到 AgentMemory
- **Cron 链式调用**：`bus.py scan && mailbus-memory-bridge.py` 一行 cron 完成扫描+记忆同步

### 测试
- 3 个测试文件（scanner / ack_handler / archiver），19 个用例全部通过
- 测试使用 mock CLI 推送，不依赖外部进程

### 文档
- README.md — 项目介绍、快速开始、配置参考
- ARCHITECTURE.md — 完整架构文档（数据流、目录结构、消息模型、安全边界）
- docs/quickstart.md — 快速开始指南
- docs/message-format.md — 消息格式参考（Agent 开发者接口文档）

### 踩坑记录
- `from_dict()` 须过滤未知字段（系统消息含 `system_info` 等额外字段）
- argparse 全局参数不继承到子命令，需每个子命令单独加
- `ensure_dir` 须早于 `json_write`（原子写入要求父目录存在）
- Popen 后台推送不要等 CLI 执行完，`start_new_session=True` 后返回即算投递
| - Message 对象 vs dict 兼容：inbox 数据中消息既有 `Message` 对象也有 dict，访问时需双形态兼容

## 1.1.0 (2026-05-22)

### 多模型 Fallback
- **模型别名系统**：`agent_types.models` 定义模型别名 → CLI 参数的映射，每个 agent 框架可配不同的参数
- **Agent 级模型配置**：`agents.<name>.models` 数组指定该 agent 可用的模型别名列表
- **自动 Fallback**：推送时按 models 顺序试，第一个启动成功的模型即用，通了就停
- **占位符系统增强**：`MODEL` 占位符自动替换为模型别名对应的 CLI 参数，没配模型时自动消除 `--model MODEL` 整段参数

### 修复
- **大力（OpenCode）不执行任务**：模板中硬编码的 `--model deepseek/deepseek-chat` 改为 `MODEL` 占位符，通过 models 别名配置注入，换模型只需改别名映射

### 配置变更
- `agent_types` 新增 `models` 字段：模型别名 → 各框架参数映射
- `agents.<name>` 新增 `models` 数组：该 agent 可用的模型别名（可选，不配则走纯文件通信）
- `agent_types.<type>.push` 模板中的模型参数改为 `MODEL` 占位符
