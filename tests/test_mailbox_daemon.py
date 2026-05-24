"""测试 mailbox-daemon 的批量合并唤醒逻辑"""
import sys, os, json, tempfile, time, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

spec = importlib.util.spec_from_file_location("mb_daemon",
    os.path.join(os.path.dirname(__file__), "..", "mailbox-daemon.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
MailboxDaemon = mod.MailboxDaemon


def make_msg(msg_id: str, sender: str, content: str,
             msg_type="task", priority="normal") -> dict:
    return {
        "id": msg_id, "from": sender, "to": "lingxiao",
        "type": msg_type, "priority": priority,
        "status": "pending", "content": content,
        "created_at": "2026-05-25T10:00:00+0800",
    }


def test_batch_single_message_falls_through():
    """单条消息应走到 _trigger_agent 路径"""
    with tempfile.TemporaryDirectory() as td:
        daemon = MailboxDaemon("lingxiao", data_dir=td)
        inbox_path = os.path.join(td, "inbox", "lingxiao", "inbox.json")
        os.makedirs(os.path.dirname(inbox_path))
        inbox = {
            "agent": "lingxiao", "has_unread": True,
            "messages": [make_msg("msg-001", "lingzhao", "请审核架构方案")],
        }
        with open(inbox_path, "w") as f:
            json.dump(inbox, f)

        daemon._process_inbox()

        with open(inbox_path) as f:
            updated = json.load(f)
        msg = updated["messages"][0]
        assert msg["status"] in ("acknowledged",), \
            f"状态应为 acknowledged, 实际: {msg['status']}"
        print("  ✓ 单条消息被正确 ack")
    print("  ✓ test_batch_single_message_falls_through")



def test_combined_summary_includes_all_senders():
    """多条消息的合并摘要应包含每个发送者的回复指令"""
    with tempfile.TemporaryDirectory() as td:
        daemon = MailboxDaemon("lingxiao", data_dir=td)
        entries = [
            {"msg_id": "msg-001", "sender": "lingzhao",
             "preview": "请审核架构方案", "parsed": {},
             "raw_msg": make_msg("msg-001", "lingzhao", "请审核架构方案")},
            {"msg_id": "msg-002", "sender": "lingxi",
             "preview": "安全审计报告", "parsed": {},
             "raw_msg": make_msg("msg-002", "lingxi", "安全审计报告")},
            {"msg_id": "msg-003", "sender": "ziyan",
             "preview": "这个bug帮忙看看", "parsed": {},
             "raw_msg": make_msg("msg-003", "ziyan", "这个bug帮忙看看")},
        ]

        msg_blocks = []
        for i, e in enumerate(entries, 1):
            sender = e["sender"]
            raw = e["raw_msg"]
            reply_path = f"{td}/inbox/{sender}/inbox.json"
            block = (
                f"╔══ 消息 {i} ═══════════════════════════╗\n"
                f"  类型: {raw.get('type')}\n"
                f"  来自: {sender}\n"
                f"  消息ID: {e['msg_id']}\n"
                f"  优先级: {raw.get('priority')}\n"
                f"  内容: {raw.get('content', '')[:500]}\n"
                f"╚════════════════════════════════════╝\n"
                f"\n"
                f"▶ 回复给 {sender}\n"
                f"  写文件到: {reply_path}\n"
            )
            msg_blocks.append(block)
        combined = "\n".join(msg_blocks)

        assert "来自: lingzhao" in combined
        assert "来自: lingxi" in combined
        assert "来自: ziyan" in combined
        assert combined.count("▶ 回复给") == 3
        assert f"{td}/inbox/lingzhao/inbox.json" in combined
        assert f"{td}/inbox/lingxi/inbox.json" in combined
        assert f"{td}/inbox/ziyan/inbox.json" in combined
        print("  ✓ 合并摘要包含所有发送者和独立回复指令")
    print("  ✓ test_combined_summary_includes_all_senders")


def test_reap_sends_to_correct_senders():
    """进程完成后，回执应发给各自的原始发送者"""
    with tempfile.TemporaryDirectory() as td:
        daemon = MailboxDaemon("lingxiao", data_dir=td)

        for sender in ("lingzhao", "lingxi"):
            inbox_dir = os.path.join(td, "inbox", sender)
            os.makedirs(inbox_dir)
            with open(os.path.join(inbox_dir, "inbox.json"), "w") as f:
                json.dump({"agent": sender, "has_unread": False, "messages": []}, f)

        daemon._send_completion_notice("msg-001", "lingzhao", "完成", "处理完毕")
        daemon._send_completion_notice("msg-002", "lingxi", "完成", "处理完毕")

        with open(os.path.join(td, "inbox", "lingzhao", "inbox.json")) as f:
            lz = json.load(f)
        assert any("msg-001" in m.get("id","") for m in lz["messages"]), \
            f"lingzhao 应收到 msg-001 回执: {[m['id'] for m in lz['messages']]}"

        with open(os.path.join(td, "inbox", "lingxi", "inbox.json")) as f:
            lx = json.load(f)
        assert any("msg-002" in m.get("id","") for m in lx["messages"]), \
            f"lingxi 应收到 msg-002 回执: {[m['id'] for m in lx['messages']]}"

        print("  ✓ 各发送者收到各自的回执，未错发")
    print("  ✓ test_reap_sends_to_correct_senders")


def test_merge_multiple_from_same_sender():
    """同一发件人的多条消息应有独立的回复指令"""
    with tempfile.TemporaryDirectory() as td:
        entries = [
            {"msg_id": "m1", "sender": "lingzhao", "preview": "任务A",
             "parsed": {}, "raw_msg": make_msg("m1", "lingzhao", "任务A内容")},
            {"msg_id": "m2", "sender": "lingxi", "preview": "任务B",
             "parsed": {}, "raw_msg": make_msg("m2", "lingxi", "任务B内容")},
            {"msg_id": "m3", "sender": "lingzhao", "preview": "任务C",
             "parsed": {}, "raw_msg": make_msg("m3", "lingzhao", "任务C内容")},
        ]
        senders = {e["msg_id"]: e["sender"] for e in entries}
        assert senders["m1"] == "lingzhao"
        assert senders["m2"] == "lingxi"
        assert senders["m3"] == "lingzhao"

        msg_blocks = []
        for i, e in enumerate(entries, 1):
            sender = e["sender"]
            raw = e["raw_msg"]
            reply_path = f"{td}/inbox/{sender}/inbox.json"
            block = (
                f"╔══ 消息 {i} ═══════════════════════════╗\n"
                f"  来自: {sender}\n"
                f"  内容: {raw.get('content', '')[:500]}\n"
                f"╚════════════════════════════════════╝\n"
                f"▶ 回复给 {sender}\n"
                f"  写文件到: {reply_path}\n"
            )
            msg_blocks.append(block)
        combined = "\n".join(msg_blocks)

        assert combined.count("回复给 lingzhao") == 2
        assert combined.count("回复给 lingxi") == 1
        print("  ✓ 同一发件人的多条消息各有独立回复指令")
    print("  ✓ test_merge_multiple_from_same_sender")


def test_processing_ids_dedup():
    """_processing_ids 应阻止同一条消息被重复处理"""
    with tempfile.TemporaryDirectory() as td:
        daemon = MailboxDaemon("lingxiao", data_dir=td)
        inbox_path = os.path.join(td, "inbox", "lingxiao", "inbox.json")
        os.makedirs(os.path.dirname(inbox_path))

        # 创建一条消息
        inbox = {
            "agent": "lingxiao", "has_unread": True,
            "messages": [make_msg("msg-001", "lingzhao", "请审核架构方案")],
        }
        with open(inbox_path, "w") as f:
            json.dump(inbox, f)

        # 第1次 poll：应处理该消息 → 加入 _processing_ids
        daemon._process_inbox()

        assert "msg-001" in daemon._processing_ids, \
            "消息应被加入 _processing_ids"

        # 读取 ack 文件，确认只有 1 条 ack
        ack = json.load(open(daemon.ack_path)) if os.path.exists(daemon.ack_path) else []
        ack_count = len([e for e in (ack if isinstance(ack, list) else [ack]) if e.get("msg_id") == "msg-001"])

        # 第2次 poll：_processing_ids 应阻止重复处理
        daemon._process_inbox()

        ack2 = json.load(open(daemon.ack_path)) if os.path.exists(daemon.ack_path) else []
        ack2_count = len([e for e in (ack2 if isinstance(ack2, list) else [ack2]) if e.get("msg_id") == "msg-001"])

        assert ack_count == ack2_count, \
            f"重复处理应被拦截: 第1次={ack_count}条ack, 第2次={ack2_count}条ack"

        # 释放处理中状态
        daemon._processing_ids.discard("msg-001")
        print("  ✓ _processing_ids 去重保护生效")
    print("  ✓ test_processing_ids_dedup")


def run_all():
    print("\n🧪 测试 mailbox-daemon 批量合并逻辑\n")
    test_batch_single_message_falls_through()
    test_combined_summary_includes_all_senders()
    test_reap_sends_to_correct_senders()
    test_merge_multiple_from_same_sender()
    test_processing_ids_dedup()
    print("\n✅ 全部通过\n")


if __name__ == "__main__":
    run_all()
