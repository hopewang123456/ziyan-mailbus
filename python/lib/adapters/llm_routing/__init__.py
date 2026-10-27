"""LLM 路由域（R3 聚合，2026-10-26）— 任务复杂度 → 模型档位 → 本地推理就绪判定。

- `model_router`      消息 → flash/pro/ollama 档位选择（默认全 flash 省 token）
- `complexity_router` 任务复杂度分层路由决策（消费 model_router 档位 + ollama 就绪）
- `ollama_routing`    GPU/ollama 本地推理就绪探测与准备

三者互为闭环，聚合为单一子域（高内聚）；对位 interfaces 暂无独立 Port，
对外一律经 composition 门面（attach_mailbus_routing 等）访问。
"""
