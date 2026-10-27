"""R4 shim (2026-10-26): HarnessContract 为两侧共享数据契约，已下沉
`lib.domain.harness_contract`（adapters/interfaces/application 均只依赖 domain）。"""
import sys

from lib.domain import harness_contract as _moved

sys.modules[__name__] = _moved
