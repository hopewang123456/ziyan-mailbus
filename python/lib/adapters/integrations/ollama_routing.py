"""R3 shim (2026-10-26): LLM 路由域聚合至 `lib.adapters.llm_routing.ollama_routing`."""
import sys

from lib.adapters.llm_routing import ollama_routing as _moved

sys.modules[__name__] = _moved
