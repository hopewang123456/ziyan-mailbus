"""
ziyan-mailbus Webhook 推送模块

为 agent 配置 webhook_url 后，总线通过 HTTP POST 推送消息，
代替传统的 CLI 推送方式。

配置示例（config.json）:
    "agents": {
        "my_service": {
            "type": "none",
            "webhook_url": "https://example.com/mailbus-webhook",
            "webhook_secret": "my-secret-key"
        }
    }
"""

import json
import hmac
import hashlib
import time
import logging
from typing import Optional
from urllib.request import Request, urlopen, install_opener, build_opener, HTTPHandler
from urllib.error import URLError, HTTPError

from .models import Message, MsgStatus
from .utils import _now_iso, log_error, resolve_paths
from .scanner import mark_as_pushed, update_message_status

logger = logging.getLogger("mailbus.webhook")

# ── 默认超时 ──────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15  # 秒


def push_via_webhook(
    data_dir: str,
    agent_name: str,
    messages: list,
    webhook_url: str,
    webhook_secret: str = "",
    max_retries: int = 3,
    auto_ack: bool = False,
) -> list:
    """
    通过 Webhook 推送消息给 agent。

    参数:
        data_dir: 数据目录
        agent_name: agent 名称
        messages: 消息列表（Message 对象或 dict）
        webhook_url: Webhook HTTP 地址
        webhook_secret: HMAC-SHA256 签名密钥（可选）
        max_retries: 最大重试次数
        auto_ack: 推送成功后直接标记 acknowledged

    返回:
        推送失败的消息 ID 列表
    """
    failed_ids = []
    paths = resolve_paths(data_dir)
    msg_ids = [m.id if not isinstance(m, dict) else m["id"] for m in messages]

    # 1. 标记为 pushed
    mark_as_pushed(data_dir, agent_name, msg_ids)

    # 2. 构建 payload
    payload_list = []
    for msg_entry in messages:
        if isinstance(msg_entry, dict):
            payload_list.append({
                "id": msg_entry.get("id"),
                "from": msg_entry.get("from"),
                "to": msg_entry.get("to"),
                "type": msg_entry.get("type"),
                "priority": msg_entry.get("priority"),
                "content": msg_entry.get("content"),
                "attachments": msg_entry.get("attachments", []),
                "status": msg_entry.get("status"),
                "state": msg_entry.get("state") or msg_entry.get("status"),
                "created_at": msg_entry.get("created_at"),
                "reply_format": msg_entry.get("reply_format", {}),
            })
        else:
            payload_list.append({
                "id": msg_entry.id,
                "from": msg_entry.from_,
                "to": msg_entry.to_,
                "type": msg_entry.type,
                "priority": msg_entry.priority,
                "content": msg_entry.content,
                "attachments": msg_entry.attachments or [],
                "status": msg_entry.status,
                "state": getattr(msg_entry, 'state', '') or msg_entry.status,
                "created_at": msg_entry.created_at,
                "reply_format": msg_entry.reply_format or {},
            })

    payload = {
        "bus": "ziyan-mailbus",
        "version": "1.0.0",
        "action": "push",
        "agent": agent_name,
        "timestamp": _now_iso(),
        "messages": payload_list,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # 3. 发送请求（带重试 + 指数退避）
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ziyan-mailbus/1.0",
        "X-Mailbus-Event": "push",
        "X-Mailbus-Agent": agent_name,
    }

    # HMAC 签名
    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Mailbus-Signature"] = f"sha256={signature}"

    last_error = ""
    success = False
    for attempt in range(1 + max_retries):  # 首次 + 重试
        if attempt > 0:
            delay = min(2 ** attempt + __import__("random").uniform(-1, 1), 30)
            delay = max(0.5, delay)
            time.sleep(delay)

        try:
            req = Request(webhook_url, data=body, headers=headers, method="POST")
            resp = urlopen(req, timeout=DEFAULT_TIMEOUT)
            status = resp.getcode()
            resp_body = resp.read().decode("utf-8", errors="replace")[:500]
            resp.close()

            if 200 <= status < 300:
                success = True
                break
            else:
                last_error = f"HTTP {status}: {resp_body}"
        except HTTPError as e:
            last_error = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
        except URLError as e:
            last_error = f"连接失败: {e.reason}"
        except Exception as e:
            last_error = f"未知错误: {e}"

    if success:
        if auto_ack:
            for mid in msg_ids:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
        else:
            for mid in msg_ids:
                update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []
    else:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.FAILED)
            log_error(paths["errors"], mid, agent_name,
                      f"Webhook 推送失败 ({max_retries + 1} 次): {last_error}")
        return msg_ids
