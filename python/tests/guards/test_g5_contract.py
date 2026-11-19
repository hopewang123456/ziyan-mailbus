"""G5 契约漂移守卫：代码导出的 OpenAPI 必须与入库发布物一致。

A1 裁决：代码即真源。更新契约的方式是重新导出，而不是手改 JSON。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import REPO_ROOT  # noqa: E402

CONTRACT_PATH = REPO_ROOT / "shared" / "contracts" / "generated" / "openapi.json"


def test_committed_openapi_matches_code() -> None:
    from mailbus.bootstrap.main import create_app

    assert CONTRACT_PATH.exists(), f"缺少契约发布物：{CONTRACT_PATH}（运行 python tools/export_openapi.py）"
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    current = create_app().openapi()
    assert committed == current, "OpenAPI 已漂移：运行 python tools/export_openapi.py 重新导出"
