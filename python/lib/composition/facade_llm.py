"""Composition facades — LLM / internal-llm domain (R2 split from composition.py).

Lazy forwarders so callers stay layer-clean. Target domain: adapters.internal_llm.*
and application.internal_llm.*.
"""
from __future__ import annotations

from typing import Any


def complete_llm(messages: list, cfg: dict, *, prefer: str | None = None):
    """Lazy Internal LLM complete (composition entry for application)."""
    from lib.adapters.internal_llm.client import complete

    return complete(messages, cfg, prefer=prefer)


def retrieve_context(
    data_dir: str,
    cfg: dict | None,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict]:
    """Lazy RAG retrieve (composition entry for application)."""
    from lib.adapters.internal_llm.index import retrieve

    return retrieve(data_dir, cfg, query, top_k=top_k)


def resolve_llm_config(raw: dict) -> dict:
    """Resolve mailbus_internal_llm config (env keys, defaults)."""
    from lib.adapters.internal_llm.config_resolve import resolve_llm_config as _resolve

    return _resolve(raw)


def llm_error_type():
    """Return LLMError exception class (for except clauses)."""
    from lib.adapters.internal_llm.client import LLMError

    return LLMError


def probe_all_internal_llm(*args: Any, **kwargs: Any):
    """Internal LLM probe — api/internal_llm_status 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.probe.probe_all`。
    """
    from lib.adapters.internal_llm.probe import probe_all as _impl

    return _impl(*args, **kwargs)


def load_llm_config_internal(*args: Any, **kwargs: Any):
    """Internal LLM 配置加载 — api/handlers_internal_llm 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.probe.load_llm_config`。
    """
    from lib.adapters.internal_llm.probe import load_llm_config as _impl

    return _impl(*args, **kwargs)


def rebuild_internal_llm_index(*args: Any, **kwargs: Any):
    """Internal LLM 索引重建 — api/handlers_internal_llm 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.index.rebuild_index`。
    """
    from lib.adapters.internal_llm.index import rebuild_index as _impl

    return _impl(*args, **kwargs)


def triage_inbox_anomaly(*args: Any, **kwargs: Any):
    """Inbox 异常分诊 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.internal_llm.triage.triage_inbox_anomaly`。
    """
    from lib.application.internal_llm.triage import triage_inbox_anomaly as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "complete_llm",
    "retrieve_context",
    "resolve_llm_config",
    "llm_error_type",
    "probe_all_internal_llm",
    "load_llm_config_internal",
    "rebuild_internal_llm_index",
    "triage_inbox_anomaly",
    "is_no_llm_notice",
]


def is_no_llm_notice(*args: Any, **kwargs: Any):
    """零 token 通知判定（msg_type 无需 LLM 即自动消化）— api/application 经此访问（分层约束）。"""
    from lib.adapters.llm_routing.model_router import is_no_llm_notice as _impl

    return _impl(*args, **kwargs)
