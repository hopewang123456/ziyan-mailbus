"""R3 shim (2026-10-26): LLM 路由域聚合至 `lib.adapters.llm_routing.model_router`."""
import sys

from lib.adapters.llm_routing import model_router as _moved

sys.modules[__name__] = _moved
