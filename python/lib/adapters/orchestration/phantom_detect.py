"""R1 shim (2026-10-26): 纯规则件已归位 `lib.application.orchestration.phantom_detect`。"""
import sys

from lib.application.orchestration import phantom_detect as _moved

sys.modules[__name__] = _moved
