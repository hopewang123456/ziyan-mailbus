"""测试 registry 加载 / domain 路由 / project 字段"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Message, MsgType, MsgStatus, Priority, Inbox
from lib.utils import (
    load_registry, resolve_domain_to_agents, clear_registry_cache,
    build_message,
)


def _make_registry(data_dir: str, data: dict):
    """辅助函数：写 registry.json"""
    path = os.path.join(data_dir, "registry.json")
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def test_load_registry_empty():
    """registry.json 不存在时返回空 registry"""
    clear_registry_cache()
    with tempfile.TemporaryDirectory() as tmp:
        reg = load_registry(tmp)
        assert reg["version"] == "1"
        assert reg["agents"] == {}


def test_load_registry_basic():
    """正常加载 registry.json"""
    clear_registry_cache()
    with tempfile.TemporaryDirectory() as tmp:
        _make_registry(tmp, {
            "version": "1",
            "agents": {
                "灵犀": {"domains": ["engineering", "research"], "role": "研究员", "skills": []},
                "小七": {"domains": ["operations"], "role": "调度员", "skills": []},
            }
        })
        reg = load_registry(tmp)
        assert reg["version"] == "1"
        assert "灵犀" in reg["agents"]
        assert "小七" in reg["agents"]
        assert "engineering" in reg["agents"]["灵犀"]["domains"]


def test_resolve_domain():
    """domain 路由正确展开 agent 列表"""
    clear_registry_cache()
    with tempfile.TemporaryDirectory() as tmp:
        _make_registry(tmp, {
            "version": "1",
            "agents": {
                "灵犀": {"domains": ["engineering", "research"]},
                "灵昭": {"domains": ["engineering"]},
                "小七": {"domains": ["operations"]},
                "一哥": {"domains": ["operations"]},
            }
        })
        reg = load_registry(tmp)
        
        eng = resolve_domain_to_agents("engineering", reg)
        assert "灵犀" in eng
        assert "灵昭" in eng
        assert "小七" not in eng
        assert "一哥" not in eng
        
        ops = resolve_domain_to_agents("operations", reg)
        assert "小七" in ops
        assert "一哥" in ops
        assert "灵犀" not in ops
        
        unknown = resolve_domain_to_agents("nonexistent", reg)
        assert unknown == []


def test_resolve_domain_all():
    """--domain ALL 返回所有有 domain 的 agent"""
    clear_registry_cache()
    with tempfile.TemporaryDirectory() as tmp:
        _make_registry(tmp, {
            "version": "1",
            "agents": {
                "灵犀": {"domains": ["engineering"]},
                "小七": {"domains": ["operations"]},
                "mailbus": {"domains": ["system"]},
            }
        })
        reg = load_registry(tmp)
        all_agents = resolve_domain_to_agents("ALL", reg)
        assert len(all_agents) == 3
        assert "灵犀" in all_agents
        assert "小七" in all_agents
        assert "mailbus" in all_agents


def test_resolve_duplicate_dedup():
    """一个 agent 属于多个 domain，同一 domain 不重复"""
    clear_registry_cache()
    with tempfile.TemporaryDirectory() as tmp:
        _make_registry(tmp, {
            "version": "1",
            "agents": {
                "灵犀": {"domains": ["engineering", "research"]},
                "灵曦": {"domains": ["engineering"]},
            }
        })
        reg = load_registry(tmp)
        result = resolve_domain_to_agents("engineering", reg)
        assert result == ["灵曦", "灵犀"]  # 字母序
        assert len(result) == 2


def test_project_field_on_message():
    """Message 的 project 字段正确序列化/反序列化"""
    msg = Message(
        id="msg-test-project-001",
        from_="lingxi",
        to="lingzhao",
        content="测试 project 字段",
        project="mailbus",
    )
    d = msg.to_dict()
    assert d.get("project") == "mailbus"
    
    # 空 project 不输出
    msg2 = Message(
        id="msg-test-no-project",
        from_="lingxi",
        to="lingzhao",
        content="无 project",
    )
    d2 = msg2.to_dict()
    assert "project" not in d2
    
    # from_dict 正确读取
    msg3 = Message.from_dict(d)
    assert msg3.project == "mailbus"


def test_build_message_with_project():
    """build_message 传入 project 字段正确构造消息"""
    with tempfile.TemporaryDirectory() as tmp:
        # 不需要 registry，只测试构造
        msg = build_message(
            from_="lingxi",
            to="lingzhao",
            content="测试",
            msg_type=MsgType.TASK,
            project="paperclip",
        )
        assert msg.project == "paperclip"
        d = msg.to_dict()
        if "project" in d:
            assert d["project"] == "paperclip"


def test_build_message_no_project():
    """不传 project 时序列化不输出"""
    msg = build_message(
        from_="lingxi",
        to="lingzhao",
        content="测试",
        msg_type=MsgType.NOTICE,
    )
    d = msg.to_dict()
    assert "project" not in d


if __name__ == "__main__":
    test_load_registry_empty()
    test_load_registry_basic()
    test_resolve_domain()
    test_resolve_domain_all()
    test_resolve_duplicate_dedup()
    test_project_field_on_message()
    test_build_message_with_project()
    test_build_message_no_project()
    print("\n✓ 所有 registry + project 测试通过\n")
