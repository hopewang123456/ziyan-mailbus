"""mailbus 后端（新栈）。

分层（只允许单向依赖）：

    core → application → adapters
                        → api
    bootstrap（组合根，可依赖以上全部）

各层职责见 docs/architecture 与 Vault 设计文档。
"""

__version__ = "2.0.0.dev0"
