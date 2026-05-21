"""
ziyan-mailbus 数据模型

定义消息状态、消息格式、队列模型、配置模型等基础数据类型。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone, timedelta
import json

# ── 消息状态 ──────────────────────────────────────────────────────────

class MsgStatus:
    """消息状态常量"""
    PENDING      = "pending"       # 已写入 inbox，等待推送
    PUSHED       = "pushed"        # 已通过 CLI 推送，等待 agent ack
    ACKNOWLEDGED = "acknowledged"  # agent 已确认收到
    FAILED       = "failed"        # 3 次重试均无 ack
    RESENDING    = "resending"     # 人工重推中（附带断线说明）
    ARCHIVED     = "archived"      # 已归档

    ALL = {PENDING, PUSHED, ACKNOWLEDGED, FAILED, RESENDING, ARCHIVED}


class Priority:
    """优先级常量"""
    NORMAL = "normal"
    URGENT = "urgent"
    ALL = {NORMAL, URGENT}


class MsgType:
    """消息类型常量"""
    TASK     = "task"       # 任务
    NOTICE   = "notice"     # 通知
    QUESTION = "question"   # 询问
    SYSTEM   = "system"     # 系统消息（初始化/告警）
    ALL = {TASK, NOTICE, QUESTION, SYSTEM}


class Level:
    """日志级别常量"""
    INFO  = "INFO"
    WARN  = "WARN"
    ERROR = "ERROR"
    ALL = {INFO, WARN, ERROR}


# ── 回复格式模板 ──────────────────────────────────────────────────────

ACK_FORMAT = {
    "action": "ack",
    "msg_id": "<消息ID>",
    "agent": "<agent名称>",
    "timestamp": "<ISO时间>",
}

MARK_READ_FORMAT = {
    "action": "mark_read",
    "msg_ids": ["<消息ID列表>"],
    "agent": "<agent名称>",
    "timestamp": "<ISO时间>",
}

FORWARD_FORMAT = {
    "action": "forward",
    "original_msg_id": "<原始消息ID>",
    "from": "<本agent>",
    "to": "<目标agent>",
    "type": "normal",
    "priority": "normal",
    "content": "...",
    "attachments": [],
    "timestamp": "<ISO时间>",
}

# ── 数据模型 ──────────────────────────────────────────────────────────

@dataclass
class ReplyFormat:
    """消息附带的回复格式说明（agent 知道怎么回复总线）"""
    ack: dict = field(default_factory=lambda: dict(ACK_FORMAT))
    mark_read: dict = field(default_factory=lambda: dict(MARK_READ_FORMAT))
    forward_target_format: str = "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json"


@dataclass
class Message:
    """单条消息"""
    id: str                         # msg-20260521-001
    from_: str                      # 发件人 agent 名
    to: str                         # 收件人 agent 名
    priority: str = Priority.NORMAL
    type: str = MsgType.NOTICE
    content: str = ""
    attachments: list = field(default_factory=list)
    reply_format: Optional[dict] = None
    status: str = MsgStatus.PENDING
    pushed_count: int = 0
    created_at: str = ""            # ISO 时间
    acknowledged_at: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["from"] = d.pop("from_")  # from_ → from（JSON 友好）
        return d

    @classmethod
    def from_dict(cls, d: dict):
        d["from_"] = d.pop("from")  # from → from_
        # 只取 Message 已知字段，忽略额外的字段
        known = {"id", "from_", "to", "priority", "type", "content",
                 "attachments", "reply_format", "status", "pushed_count",
                 "created_at", "acknowledged_at"}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


@dataclass
class Inbox:
    """Agent 邮箱"""
    agent: str
    has_unread: bool = False
    messages: list = field(default_factory=list)   # list[Message]
    since: str = ""

    def to_dict(self):
        return {
            "agent": self.agent,
            "has_unread": self.has_unread,
            "messages": [m.to_dict() if isinstance(m, Message) else m for m in self.messages],
            "since": self.since or _now_iso(),
        }

    @classmethod
    def from_dict(cls, d: dict):
        inbox = cls(agent=d["agent"], has_unread=d.get("has_unread", False), since=d.get("since", ""))
        inbox.messages = [Message.from_dict(m) if isinstance(m, dict) else m for m in d.get("messages", [])]
        return inbox


@dataclass
class AgentConfig:
    """配置文件中单个 agent 的配置"""
    name: str
    role: str = ""
    cli: str = ""
    inbox: str = ""


@dataclass
class BusConfig:
    """总线配置"""
    project: str = "ziyan-mailbus"
    version: str = "1.0.0"
    data_dir: str = "/mnt/e/ai_tools/mail/store"
    ack_timeout: int = 30           # 等待 ack 超时（秒）
    max_retries: int = 3            # 最大重试次数
    archive_days: int = 7           # 归档天数
    archive_max_messages: int = 300 # inbox 最大消息数
    agents: dict = field(default_factory=dict)  # name → AgentConfig


# ── 工具函数 ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    """返回当前时间的 ISO 格式字符串（本地时间 +08:00）"""
    # UTC+8
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S%z")


def generate_msg_id() -> str:
    """生成唯一消息 ID: msg-20260521-XXXXX"""
    now = datetime.now()
    date_part = now.strftime("%Y%m%d")
    seq = int(now.timestamp() * 1000) % 100000
    return f"msg-{date_part}-{seq:05d}"


def is_priority_urgent(content: str, priority: str) -> bool:
    """
    判断消息是否应归为加急。
    规则：发信人标记 priority=urgent → 加急
          content 中包含明确的"紧急"字样 → 加急
          不自行推测其他关键词
    """
    if priority == Priority.URGENT:
        return True
    if "紧急" in content:
        return True
    return False
