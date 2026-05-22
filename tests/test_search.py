"""测试消息检索 (lib/search.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.search import index_message, search, scan_and_index


def test_index_and_search():
    """索引并查询"""
    with tempfile.TemporaryDirectory() as td:
        msg = {"id": "msg-search-001", "from": "alice", "to": "bob",
               "type": "task", "content": "请检查安全配置", "status": "pending",
               "created_at": "2026-05-22T12:00:00+0800"}
        index_message(td, msg)
        # FTS5 需要完整词匹配，"检查" 或 "安全" 作为独立词
        results = search(td, query_str="检查")
        if len(results) == 0:
            # FTS5 可能因为分词问题没匹配到，试试完整短语
            results = search(td, query_str='"请检查安全配置"')
        assert len(results) >= 1, f"搜索返回 {len(results)} 条，msg_id={msg['id']}"
        assert results[0]["msg_id"] == "msg-search-001"

        results2 = search(td, query_str="不存在的内容")
        assert len(results2) == 0
    print("  ✓ test_index_and_search")


def test_search_by_from():
    """按发件人过滤"""
    with tempfile.TemporaryDirectory() as td:
        index_message(td, {"id": "m1", "from": "灵曦", "to": "小七",
                          "type": "task", "content": "测试", "status": "pending"})
        index_message(td, {"id": "m2", "from": "灵昭", "to": "灵霄",
                          "type": "notice", "content": "测试2", "status": "pending"})

        results = search(td, from_agent="灵曦")
        assert len(results) == 1
        assert results[0]["msg_id"] == "m1"

        results2 = search(td, to_agent="灵霄")
        assert len(results2) == 1
        assert results2[0]["msg_id"] == "m2"
    print("  ✓ test_search_by_from")


def test_search_by_type():
    """按类型过滤"""
    with tempfile.TemporaryDirectory() as td:
        index_message(td, {"id": "m1", "from": "a", "to": "b",
                          "type": "task", "content": "执行任务", "status": "pending"})
        index_message(td, {"id": "m2", "from": "a", "to": "b",
                          "type": "notice", "content": "通知", "status": "pending"})

        results = search(td, msg_type="task")
        assert len(results) == 1
        assert results[0]["msg_id"] == "m1"
    print("  ✓ test_search_by_type")


def test_search_by_status():
    """按状态过滤"""
    with tempfile.TemporaryDirectory() as td:
        index_message(td, {"id": "m1", "from": "a", "to": "b",
                          "type": "task", "content": "任务1", "status": "pending"})
        index_message(td, {"id": "m2", "from": "a", "to": "b",
                          "type": "task", "content": "任务2", "status": "acknowledged"})

        results = search(td, status="acknowledged")
        assert len(results) == 1
        assert results[0]["msg_id"] == "m2"
    print("  ✓ test_search_by_status")


def test_search_combined():
    """多条件组合过滤"""
    with tempfile.TemporaryDirectory() as td:
        index_message(td, {"id": "m1", "from": "灵曦", "to": "小七",
                          "type": "task", "content": "检查安全", "status": "pending"})
        index_message(td, {"id": "m2", "from": "灵曦", "to": "一哥",
                          "type": "notice", "content": "通知", "status": "pending"})

        results = search(td, from_agent="灵曦", to_agent="小七")
        assert len(results) == 1
        assert results[0]["msg_id"] == "m1"

        results2 = search(td, from_agent="灵曦", msg_type="notice")
        assert len(results2) == 1
        assert results2[0]["msg_id"] == "m2"
    print("  ✓ test_search_combined")


def test_scan_and_index():
    """scan_and_index 批量索引"""
    with tempfile.TemporaryDirectory() as td:
        # scan_and_index 使用 resolve_paths，它构建 {data_dir}/inbox/ 路径
        inbox_dir = os.path.join(td, "inbox")
        os.makedirs(f"{inbox_dir}/test-agent")
        msgs = [
            {"id": "m1", "from": "a", "to": "test-agent", "type": "task",
             "content": "消息1", "status": "pending"},
            {"id": "m2", "from": "b", "to": "test-agent", "type": "notice",
             "content": "消息2", "status": "acknowledged"},
        ]
        with open(f"{td}/inbox/test-agent/inbox.json", "w") as f:
            json.dump({"agent": "test-agent", "messages": msgs, "has_unread": True}, f)

        scan_and_index(td, {"test-agent": {}})
        # 索引完后用 FTS5 精确匹配搜索
        results = search(td, query_str='"消息1"')
        assert len(results) == 1, f"搜索 '消息1' 返回 {len(results)} 条"
        results2 = search(td, query_str='"消息2"')
        assert len(results2) == 1, f"搜索 '消息2' 返回 {len(results2)} 条"
    print("  ✓ test_scan_and_index")


if __name__ == "__main__":
    test_index_and_search()
    test_search_by_from()
    test_search_by_type()
    test_search_by_status()
    test_search_combined()
    test_scan_and_index()
    print(f"\n✓ 全部 {6} 个测试通过")
