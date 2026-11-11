"""D16 批3：java 写出的 inbox.json 必须能被 python 直读消费（跨语言格式契约）。

fixture 与 java `PythonInboxWriterTest.appendWritesPythonFormat...` 断言的输出逐键一致
（id/from/to/type/priority/content/attachments/state/status/created_at/pushed_count…）。
"""
import json
from pathlib import Path

from lib.domain.models import Inbox, get_msg_state


def _java_writer_document(agent: str = "a") -> dict:
    """Java PythonInboxWriter.append 落盘形状（+0800 无冒号偏移、state/status 双轨）。"""
    return {
        "agent": agent,
        "has_unread": True,
        "since": "2026-11-11T10:00:00+0800",
        "messages": [
            {
                "id": "msg-20261111-00123",
                "from": "lingyun",
                "to": agent,
                "type": "task",
                "priority": "high",
                "content": "hello from java",
                "attachments": [],
                "state": "pending",
                "status": "pending",
                "created_at": "2026-11-11T10:00:00+0800",
                "pushed_count": 0,
                "task_id": "",
                "step_id": "",
                "contract_path": "",
            }
        ],
    }


def _write(tmp_path: Path, doc: dict) -> Inbox:
    inbox_dir = tmp_path / "inbox" / doc["agent"]
    inbox_dir.mkdir(parents=True)
    (inbox_dir / "inbox.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return Inbox.from_dict(json.loads((inbox_dir / "inbox.json").read_text(encoding="utf-8")))


def test_java_written_message_is_consumable_by_python(tmp_path: Path) -> None:
    inbox = _write(tmp_path, _java_writer_document())

    assert inbox.agent == "a"
    assert len(inbox.messages) == 1
    msg = inbox.messages[0]
    assert get_msg_state(msg) == "pending"
    assert msg.content == "hello from java"
    assert msg.type == "task"
    assert msg.priority == "high"
    assert inbox.has_unread_messages() is True


def test_java_written_message_flows_python_state_machine(tmp_path: Path) -> None:
    inbox = _write(tmp_path, _java_writer_document())

    # python pusher 语义
    assert inbox.set_msg_status("msg-20261111-00123", "pushed", state="pushed")
    assert get_msg_state(inbox.messages[0]) == "pushed"
    assert inbox.has_unread_messages() is True

    # python ack 语义（task → processing）
    inbox.set_msg_status("msg-20261111-00123", "acknowledged", state="processing")
    assert get_msg_state(inbox.messages[0]) == "processing"
    assert inbox.has_unread_messages() is True

    # 终态
    inbox.set_msg_status("msg-20261111-00123", "acknowledged", state="done")
    assert inbox.has_unread_messages() is False
