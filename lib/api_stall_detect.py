"""检测 agent CLI 因网络 / API 不可达而停滞。"""

from __future__ import annotations

import os
import re
from typing import Optional

from .utils import json_read

# 小写匹配子串（reply / stderr 聚合文本）
API_STALL_MARKERS = (
    "econnrefused",
    "connection refused",
    "connection reset",
    "connection error",
    "network error",
    "network unreachable",
    "fetch failed",
    "failed to fetch",
    "unable to connect",
    "socket hang up",
    "socket timeout",
    "api error",
    "rate limit",
    "rate_limit",
    "timed out",
    "timeout",
    "etimedout",
    "enotfound",
    "econnreset",
    "name resolution",
    "dns lookup",
    "503 service unavailable",
    "502 bad gateway",
    "504 gateway",
    "deepseek-gateway",
    "openai api",
    "unauthorized",
    "invalid api key",
    "authentication failed",
    "tls handshake",
    "ssl error",
    "no route to host",
    "temporarily unavailable",
)

_CODEX_ERROR_TYPES = re.compile(
    r'"type"\s*:\s*"(?:error|turn\.failed|thread\.failed)"',
    re.I,
)


def api_stall_config(config: Optional[dict] = None, data_dir: str = "") -> dict:
    if config is None and data_dir:
        config = json_read(os.path.join(data_dir, "config.json"), {})
    ops = (config or {}).get("pipeline_ops") or {}
    stall = ops.get("api_stall") or {}
    if not isinstance(stall, dict):
        stall = {}
    return stall


def api_stall_repush_wait_minutes(config: Optional[dict] = None, data_dir: str = "") -> float:
    stall = api_stall_config(config, data_dir)
    return float(stall.get("repush_wait_minutes", 5))


def detect_api_stall(reply_text: str) -> Optional[str]:
    """若文本含 API/网络失败特征，返回简短原因；否则 None。"""
    body = (reply_text or "").strip()
    if not body:
        return None
    low = body.lower()
    for marker in API_STALL_MARKERS:
        if marker in low:
            return f"api_network:{marker}"
    if _CODEX_ERROR_TYPES.search(body):
        if any(x in low for x in ("connect", "network", "timeout", "fetch", "gateway", "api")):
            return "api_network:codex_error_event"
    return None


def read_reply_text_for_agent(data_dir: str, agent_name: str, msg_id: str = "") -> str:
    """读取 replies/{agent}.json 最近回复（可按 msg_id 过滤）。"""
    path = os.path.join(data_dir, "replies", f"{agent_name}.json")
    if not os.path.isfile(path):
        return ""
    data = json_read(path, {})
    if not isinstance(data, dict):
        return ""
    mids = data.get("msg_ids") or []
    if msg_id and mids and msg_id not in mids:
        return ""
    return str(data.get("reply") or "")
