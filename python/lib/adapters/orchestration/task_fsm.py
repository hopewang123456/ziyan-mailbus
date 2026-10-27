"""R1 shim (2026-10-26): task_fsm 应用服务已归位 `lib.application.orchestration.task_fsm`。

本模块保留旧导入路径兼容（调用方零改动）；模块替换使所有属性访问与
`from ... import X` 与新位置完全等价。后续 R3 分包时可让调用方逐批切换。
"""
import sys

from lib.application.orchestration import task_fsm as _moved

sys.modules[__name__] = _moved
