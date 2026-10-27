"""R3 shim (2026-10-26): LLM 路由域聚合至 `lib.adapters.llm_routing.complexity_router`."""
import sys

from lib.adapters.llm_routing import complexity_router as _moved

sys.modules[__name__] = _moved
