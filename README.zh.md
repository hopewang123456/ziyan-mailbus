# ziyan-mailbus

文件级 **Agent-to-Agent** 消息总线。不绑定单一框架：通过 Adapter 接入 Hermes / OpenClaw / Codex / OpenCode / Claude Code 等。

无需 Redis / RabbitMQ —— 消息存 JSON，CLI 推送，Agent 回 ack。

## 环境

- Python ≥ 3.10
- 可选：Docker、Ollama（本机路由）、AgentMemory
- 至少一个 Agent CLI 或 A2A 端点

## 快速开始

```bash
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
pip install -e .

mailbus init --data-dir ./store
mailbus serve --host 0.0.0.0 --port 9814 --data-dir ./store

mailbus send agent-a --msg "你好" --from agent-b --data-dir ./store
mailbus status --data-dir ./store
```

将 [`migrate/env.template`](migrate/env.template) 复制为 `.env` 并填写密钥/路径。**不要提交 `.env`。**

### LLM / Ollama

首次启动优先使用本机 Ollama（未配置时取 Ollama 列表中的第一个模型）。  
若既无 Ollama 也无云端 API Key，驾驶舱会提示配置。

### 公共 Docker（最小栈）

```bash
cd docker-agents
docker compose -f compose.public.yml up -d --build
```

完整本地团队栈请继续用 `docker-compose.yml` + 本机 `docker-compose.override.yml`（不入库）。

## Demo Agent

公开示例使用通用 id：`agent-a` / `agent-b` / `agent-c`。  
见 [`examples/demo-roster.json`](examples/demo-roster.json)。

在驾驶舱 **配置中心** 注册自己的 Agent；自动发现后默认 **不启用**，需手动 enable。

## 驾驶舱

`mailbus serve` 后打开 `http://127.0.0.1:9814/`。旧版 UI：`/legacy`。

## 许可证

MIT
