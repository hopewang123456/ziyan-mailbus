"""Locale: error code → Chinese message (Q9 + Wave3 transport)."""
from __future__ import annotations

from lib.domain.error_codes import ALL_TRANSPORT_CODES

ERROR_ZH: dict[str, str] = {
    "mailbus_error": "邮件总线错误",
    "retryable": "可重试错误，请稍后重试",
    "fatal": "致命错误",
    "needs_human": "需要人工处理",
    "lock_busy": "资源锁定中，请稍后重试",
    "unauthorized": "未授权",
    "write_auth_required": "写操作需要鉴权配置",
    "framework_or_role_disabled": "框架或角色已禁用",
    "budget_paused": "链路日预算已暂停，请确认 Ollama 或恢复预算",
    "escalation_needed": "重试已达上限，需人工升级处理",
    # Wave3 transport / observability
    "transport_retryable": "传输可重试失败，将自动重试或回退",
    "transport_fatal": "传输致命失败，请检查通道配置",
    "transport_timeout": "传输超时",
    "transport_http": "HTTP 传输错误",
    "transport_a2a": "A2A 通道错误",
    "transport_webhook": "Webhook 通道错误",
    "transport_file_bus": "文件总线投递失败",
    "transport_channel_unknown": "未知传输通道",
    "delivery_failed": "消息投递失败",
    "a2a_fallback": "A2A 失败已回退到文件总线",
}


def message_zh(code: str, fallback: str = "") -> str:
    return ERROR_ZH.get(code) or fallback or code


def transport_codes_covered() -> bool:
    """Doctor/clinic: locale 覆盖全部 transport 稳定码。"""
    return all(c in ERROR_ZH for c in ALL_TRANSPORT_CODES)
