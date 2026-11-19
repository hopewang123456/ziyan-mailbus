"""指标清单读取：以 shared/config/mailbus/metrics-manifest.json 为口径来源。"""

from __future__ import annotations

import json
from pathlib import Path


class MetricsManifest:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"metrics": [], "note": f"指标清单不可用：{self._path}"}
