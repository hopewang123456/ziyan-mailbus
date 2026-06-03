"""
ziyan-mailbus 数据模型

定义消息状态、消息格式、队列模型、配置模型等基础数据类型。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone, timedelta
import json
from .constants import DEFAULT_DATA_DIR, _now_iso

# ── 消息状态 ──────────────────────────────────────────────────────────

class MsgStatus:
    """消息状态常量"""
    PENDING      = "pending"       # 已写入 inbox，等待推送
    PUSHED       = "pushed"        # 已通过 CLI 推送，等待 agent ack
    ACKNOWLEDGED = "acknowledged"  # agent 已确认收到
    FAILED       = "failed"        # 3 次重试均无 ack
    RESENDING    = "resending"     # 人工重推中（附带断线说明）
    ARCHIVED     = "archived"      # 已归档
    
    # v3.0 任务状态（替代 status 在 task 类型消息中的使用）
    RECEIVED     = "received"      # agent 已收到并 ack
    PROCESSING   = "processing"    # 正在处理中
    DONE         = "done"          # 处理完成
    CLOSED       = "closed"        # 已关闭归档
    REJECTED     = "rejected"      # 无法处理退回

    ALL = {PENDING, PUSHED, ACKNOWLEDGED, FAILED, RESENDING, ARCHIVED,
           RECEIVED, PROCESSING, DONE, CLOSED, REJECTED}


class Priority:
    """优先级常量"""
    NORMAL = "normal"
    URGENT = "urgent"
    ALL = {NORMAL, URGENT}


class MsgType:
    """消息类型常量（标准化枚举）"""
    # 基础类型
    NOTICE        = "notice"         # 公告/通知 — ack + 存记忆
    TASK          = "task"           # 纯任务 — ack + 执行
    TASK_REPLY    = "task_reply"     # 需回复的任务 — ack + 执行 + 回复发件人
    QUESTION      = "question"       # 询问 — ack + 回复发件人
    FORWARD       = "forward"        # 需转发 — ack + 转发给目标
    FORWARD_REPLY = "forward_reply"  # 需转发+回复 — ack + 转发 + 回复发件人
    BROADCAST     = "broadcast"      # 全员公告 — ack + 存记忆
    SYSTEM        = "system"         # 系统消息 — ack
    ERROR_REPORT  = "error_report"   # 错误回执 — ack + 更新任务状态

    ALL = {NOTICE, TASK, TASK_REPLY, QUESTION, FORWARD, FORWARD_REPLY,
           BROADCAST, SYSTEM, ERROR_REPORT}

    # 根据 type 推断默认 action
    @staticmethod
    def default_action(msg_type: str) -> dict:
        base = {"ack": True, "store_memory": True}
        if msg_type == MsgType.NOTICE:
            return {**base, "reply_to": "", "execute": False, "forward_to": []}
        elif msg_type == MsgType.TASK:
            return {**base, "reply_to": "", "execute": True, "forward_to": []}
        elif msg_type == MsgType.TASK_REPLY:
            return {**base, "reply_to": None, "execute": True, "forward_to": []}  # reply_to 由发信时填入
        elif msg_type == MsgType.QUESTION:
            return {**base, "reply_to": None, "execute": False, "forward_to": []}
        elif msg_type == MsgType.FORWARD:
            return {**base, "reply_to": "", "execute": False, "forward_to": []}
        elif msg_type == MsgType.FORWARD_REPLY:
            return {**base, "reply_to": None, "execute": False, "forward_to": []}
        elif msg_type == MsgType.BROADCAST:
            return {**base, "reply_to": "", "execute": False, "forward_to": []}
        elif msg_type == MsgType.SYSTEM:
            return {**base, "store_memory": False, "reply_to": "", "execute": False, "forward_to": []}
        elif msg_type == MsgType.ERROR_REPORT:
            return {**base, "reply_to": "", "execute": False, "forward_to": []}
        return {**base, "reply_to": "", "execute": False, "forward_to": []}


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
    forward_target_format: str = f"{DEFAULT_DATA_DIR}/inbox/<目标agent>/inbox.json"


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
    # v2.0 新增字段
    action: Optional[dict] = None   # {ack, reply_to, execute, forward_to, store_memory}
    task: Optional[dict] = None     # {summary, assignee, status, deadline, deliverable}
    forward_chain: Optional[dict] = None  # {root_id, hops: [{agent, action, at}], status}
    # v4.0 项目关联字段
    project: Optional[str] = None          # 所属项目（如 "mailbus", "paperclip"）
    # v3.0 任务状态机字段
    state: str = ""                 # 任务流转状态：received/processing/done/closed/rejected
    state_history: list = field(default_factory=list)  # [{state, at}, ...]
    actions: list = field(default_factory=list)  # [{step, status, at}, ...]
    received_at: Optional[str] = None
    done_at: Optional[str] = None
    done_note: str = ""                # 完成备注（由 daemon 写入）
    # v3.0 超时催办字段
    timeout_minutes: Optional[int] = None  # 超时分钟数
    escalate_to: Optional[str] = None      # 超时后通知谁（默认发件人）
    reminded_count: int = 0                # 已催办次数
    last_reminded_at: Optional[str] = None # 上次催办时间

    def __post_init__(self):
        # 没配 action 的根据 type 自动推断
        if self.action is None:
            self.action = MsgType.default_action(self.type)
            # reply_to 如果是 None 表示"需要回复发件人"，改为实际发件人
            if self.action.get("reply_to") is None:
                self.action["reply_to"] = self.from_
        # 没配 forward_chain 的自动初始化
        if self.forward_chain is None and isinstance(self.action, dict) and self.action.get("forward_to"):
            self.forward_chain = {
                "root_id": self.id,
                "hops": [{"agent": self.from_, "action": "发起", "at": self.created_at or ""}],
                "status": "in_progress",
            }

    def to_dict(self):
        d = asdict(self)
        d["from"] = d.pop("from_")  # from_ → from（JSON 友好）
        # 迁移：如果 state 为空但 status 有值，用 status 作为 state
        if not d.get("state") and d.get("status"):
            d["state"] = d["status"]
        # 清理空字段保持 JSON 干净
        for drop_key in ["state_history", "actions", "received_at", "done_at",
                          "timeout_minutes", "escalate_to", "reminded_count", "last_reminded_at",
                          "done_note"]:
            if drop_key in d and not d[drop_key]:
                if drop_key in ("state_history", "actions"):
                    if not d[drop_key]:
                        d.pop(drop_key, None)
                else:
                    d.pop(drop_key, None)
        if d.get("action"):
            # 只清理那些真正没意义的字段（全 null 或全空的不常见）
            pass
        if not d.get("task"):
            d.pop("task", None)
        if not d.get("forward_chain"):
            d.pop("forward_chain", None)
        if not d.get("project"):
            d.pop("project", None)
        return d

    @classmethod
    def from_dict(cls, d: dict):
        # 防御: from 字段缺失时用 unknown
        if "from" not in d:
            d["from"] = "unknown"
        d["from_"] = d.pop("from")  # from → from_
        # 防御: to 字段是数组时取第一个元素
        if isinstance(d.get("to"), list):
            d["to"] = d["to"][0] if d["to"] else ""
        # 防御: to 字段缺失时用空字符串
        if "to" not in d:
            d["to"] = ""
        # 防御: action/forward_chain/task 等 dict 字段可能是空字符串而非 dict
        for _dict_field in ["action", "forward_chain", "task", "reply_format"]:
            if _dict_field in d and not isinstance(d[_dict_field], dict):
                d[_dict_field] = {}
        known = {"id", "from_", "to", "priority", "type", "content",
                 "attachments", "reply_format", "status", "pushed_count",
                 "created_at", "acknowledged_at", "action", "task", "forward_chain",
                 "project",
                 "state", "state_history", "actions", "received_at", "done_at",
                 "timeout_minutes", "escalate_to", "reminded_count", "last_reminded_at",
                 "done_note"}
        filtered = {k: v for k, v in d.items() if k in known}
        # 缺 id 的自动生成
        if "id" not in filtered or not filtered["id"]:
            ts = int(datetime.now(timezone.utc).timestamp())
            filtered["id"] = f"auto-{ts}-{hash(d.get('from_', '')) % 10000:04d}"
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
        agent = d.get("agent", "")
        if not agent:
            # 容错：从 messages 第一条的 to/from 推断 agent，或者留空
            msgs = d.get("messages", [])
            if msgs:
                first = msgs[0] if isinstance(msgs[0], dict) else msgs[0].to_dict()
                agent = first.get("to", first.get("from", ""))
            d["agent"] = agent
        inbox = cls(agent=agent, has_unread=d.get("has_unread", False), since=d.get("since", ""))
        inbox.messages = [Message.from_dict(m) if isinstance(m, dict) else m for m in d.get("messages", [])]
        return inbox

    # ── 统一消息访问器（消除 isinstance 判断） ──

    def get_msg(self, msg_id: str) -> Optional["Message"]:
        """安全获取单条消息（返回 Message 对象）"""
        for m in self.messages:
            m_obj = Message.from_dict(m) if isinstance(m, dict) else m
            if m_obj.id == msg_id:
                return m_obj
        return None

    def set_msg_status(self, msg_id: str, status: str, **extra) -> bool:
        """安全更新消息状态（同时更新 dict 和 Message 对象）"""
        for i, m in enumerate(self.messages):
            mid = m.get("id") if isinstance(m, dict) else m.id
            if mid == msg_id:
                if isinstance(m, dict):
                    m["status"] = status
                    for k, v in extra.items():
                        m[k] = v
                else:
                    m.status = status
                    for k, v in extra.items():
                        if hasattr(m, k):
                            setattr(m, k, v)
                return True
        return False

    def has_unread_messages(self) -> bool:
        """检查是否有未读消息（优先检查 state，回退读 status）
        
        P4: processing 视为活跃状态（未完成），不视为已读。
        只有 terminal 态（done/closed/rejected/failed/archived）才视为已处理。
        """
        for m in self.messages:
            state = m.get("state") if isinstance(m, dict) else getattr(m, 'state', '')
            if not state:
                state = m.get("status") if isinstance(m, dict) else m.status
            # terminal 态 → 已处理
            if state in ("done", "closed", "rejected", "failed", "archived", "sent"):
                continue
            return True
        return False

    def msg_field(self, msg: object, field: str, default=None):
        """安全读取消息字段（兼容 dict 和 Message 对象）"""
        if isinstance(msg, dict):
            return msg.get(field, default)
        return getattr(msg, field, default)

    def set_msg_field(self, msg: object, field: str, value):
        """安全设置消息字段（兼容 dict 和 Message 对象）"""
        if isinstance(msg, dict):
            msg[field] = value
        else:
            setattr(msg, field, value)


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
    data_dir: str = field(default_factory=lambda: DEFAULT_DATA_DIR)
    ack_timeout: int = 30           # 等待 ack 超时（秒）
    max_retries: int = 3            # 最大重试次数
    archive_days: int = 7           # 归档天数
    archive_max_messages: int = 300 # inbox 最大消息数
    agents: dict = field(default_factory=dict)  # name → AgentConfig


# ── 工具函数 ──────────────────────────────────────────────────────────


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
