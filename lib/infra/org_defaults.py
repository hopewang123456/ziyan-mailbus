"""组织默认指派 — SoT: store/config.json 的 org_defaults 段。

个人名册（历史个人 agent id 等）禁止硬编码进业务代码：统一从这里读取。
运行时优先级：
  1. ``store/config.json → org_defaults``（由 ``init-store`` 从 ``config/mailbus/base.json`` 聚合，
     本地可通过 store 覆盖成自己的名册）
  2. 内置通用 demo 名（``agent-a`` / ``agent-b`` …），保证开源克隆后开箱可跑。

key 约定（均为可选）：
  - ``reviewer``          默认审查人（原 audit_dispatch.AUDIT_REVIEWER）
  - ``escalate_agent``    默认升级目标（原 inbox scanner escalate_to）
  - ``notify_agent``      默认通知/告警目标（原 a2a_poll notify）
  - ``notify_agents``     默认告警通知名单（列表；alerter 使用）
  - ``scheduler``         默认调度员
  - ``finance_followup``  财务跟进默认目标
  - ``audit_reviewers``   可提交审计的审查人名单（默认同 reviewer）
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, List

from lib.infra.utils import json_read


# 通用 demo fallback：不含任何个人名册
_DEFAULT_ORG: dict[str, Any] = {
    "reviewer": "agent-a",
    "escalate_agent": "agent-a",
    "notify_agent": "agent-a",
    "notify_agents": ["agent-a", "agent-m"],
    "scheduler": "agent-b",
    "finance_followup": "agent-c",
    "audit_reviewers": ["agent-a", "agent-f"],
}


def _config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "config.json")


@lru_cache(maxsize=8)
def _load_org_defaults_cached(path: str, mtime: float) -> dict[str, Any]:
    cfg = json_read(path, {})
    org = cfg.get("org_defaults") or {}
    if not isinstance(org, dict):
        return dict(_DEFAULT_ORG)
    merged = dict(_DEFAULT_ORG)
    merged.update({k: v for k, v in org.items() if v})
    return merged


def load_org_defaults(data_dir: str = "") -> dict[str, Any]:
    """加载 org_defaults（merge 内置 demo fallback）。"""
    if not data_dir:
        return dict(_DEFAULT_ORG)
    path = _config_path(data_dir)
    if not os.path.isfile(path):
        return dict(_DEFAULT_ORG)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return dict(_load_org_defaults_cached(path, mtime))


def org_default(data_dir: str, key: str, fallback: str = "") -> str:
    """读取单个默认指派 key；未配置则用 fallback，再退回内置 demo 值。"""
    org = load_org_defaults(data_dir)
    val = org.get(key)
    if val:
        return str(val)
    return fallback or str(_DEFAULT_ORG.get(key, ""))


def org_default_list(data_dir: str, key: str) -> List[str]:
    """读取列表型默认指派 key；返回去空后的非空列表。"""
    org = load_org_defaults(data_dir)
    val = org.get(key)
    if isinstance(val, list):
        return [str(v) for v in val if str(v).strip()]
    if val:
        return [str(val)]
    default = _DEFAULT_ORG.get(key)
    if isinstance(default, list):
        return [str(v) for v in default if str(v).strip()]
    return [str(default)] if default else []


def clear_org_defaults_cache() -> None:
    _load_org_defaults_cached.cache_clear()
