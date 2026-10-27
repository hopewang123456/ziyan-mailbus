"""Composition facades — transport / results domain (R2 split).

Target domain: adapters.results.* + adapters.transport.* + application transport
bridges (ack scanning / forward files / delivery normalization / outbound send).
"""
from __future__ import annotations

from typing import Any


def scan_ack_files(data_dir: str, agents: dict) -> int:
    from lib.adapters.results.ack_handler import scan_ack_files as _scan

    return _scan(data_dir, agents)


def process_ack_entry(data_dir: str, agent_name: str, ack_data: dict) -> bool:
    """单条 ack 立即处理（CLI ack 提交即生效，不等调度器）。"""
    from lib.adapters.results.ack_handler import process_ack as _process

    return _process(data_dir, agent_name, ack_data)


def process_mark_read_entry(data_dir: str, agent_name: str, mark_data: dict) -> bool:
    """单条 mark_read 立即处理。"""
    from lib.adapters.results.ack_handler import process_mark_read as _process

    return _process(data_dir, agent_name, mark_data)


def scan_forward_files(data_dir: str, agents: dict) -> int:
    from lib.adapters.results.ack_handler import scan_forward_files as _scan

    return _scan(data_dir, agents)


def scan_error_reports(data_dir: str, agents: dict) -> list:
    # 实际实现下沉到 application 层（2026-09 治理）；
    # adapter→application 跨层违规修复，composition 直接调 application 服务。
    from lib.application.orchestration.error_reports import scan_and_apply_error_reports

    return scan_and_apply_error_reports(data_dir, agents)


def normalize_opencode_deliveries(*args: Any, **kwargs: Any):
    """OpenCode 交付归一化 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.transport.delivery_normalizer.normalize_opencode_deliveries`。
    """
    from lib.application.transport.delivery_normalizer import normalize_opencode_deliveries as _impl

    return _impl(*args, **kwargs)


def send_outbound(*args: Any, **kwargs: Any):
    """外发消息发送 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.transport_send.send_outbound`。
    """
    from lib.application.transport_send import send_outbound as _impl

    return _impl(*args, **kwargs)


def list_unacked(*args: Any, **kwargs: Any) -> list:
    from lib.adapters.results.ack import list_unacked as _fn

    return list(_fn(*args, **kwargs))


__all__ = [
    "scan_ack_files",
    "process_ack_entry",
    "process_mark_read_entry",
    "scan_forward_files",
    "scan_error_reports",
    "normalize_opencode_deliveries",
    "send_outbound",
    "list_unacked",
]
