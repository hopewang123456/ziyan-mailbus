"""metrics manifest 读取 — 双栈唯一口径真源（B1）。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read

_DEFAULT_PATH = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "metrics-manifest.json")


@lru_cache(maxsize=4)
def _load(path: str) -> Dict[str, Any]:
    return json_read(path, {"metrics": []})


def load_manifest(data_dir: str = "") -> Dict[str, Any]:
    """store 覆盖优先（{data_dir}/config/metrics-manifest.json），否则 shared seed。"""
    if data_dir:
        p = os.path.join(data_dir, "config", "metrics-manifest.json")
        if os.path.isfile(p):
            return _load(os.path.abspath(p))
    return _load(_DEFAULT_PATH)


def metric_entry(metric_id: str, data_dir: str = "") -> Optional[Dict[str, Any]]:
    for m in load_manifest(data_dir).get("metrics") or []:
        if m.get("id") == metric_id:
            return m
    return None


def metric_ids(data_dir: str = "") -> List[str]:
    return [str(m.get("id")) for m in load_manifest(data_dir).get("metrics") or []]
