"""
gateway_mail.py 单元测试

覆盖：_get_password / _connect_imap / route_email / run_once
"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway_mail import _get_password, route_email, run_once


def test_get_password_env():
    """优先读取环境变量 MAILBUS_MAIL_PASSWORD"""
    os.environ["MAILBUS_MAIL_PASSWORD"] = "env-secret"
    cfg = {"password": "cfg-secret"}
    assert _get_password(cfg) == "env-secret"
    del os.environ["MAILBUS_MAIL_PASSWORD"]


def test_get_password_fallback():
    """无环境变量时用配置中的密码"""
    cfg = {"password": "cfg-secret"}
    assert _get_password(cfg) == "cfg-secret"


def test_get_password_empty():
    """密码为空时返回空字符串"""
    assert _get_password({}) == ""


def test_route_email_no_mapping():
    """没有 agent_mapping 时返回 None"""
    with tempfile.TemporaryDirectory() as tmp:
        mail = {"to": "test@example.com", "from": "sender@x.com",
                "subject": "Hello", "body": "Hi", "id": "email-001"}
        config = {"mail": {}}
        result = route_email(mail, config, tmp)
        assert result is None


def test_route_email_match():
    """匹配收件地址时写入 inbox 并返回 agent 名称"""
    with tempfile.TemporaryDirectory() as tmp:
        agent = "lingzhao"
        inbox_dir = os.path.join(tmp, "inbox", agent)
        os.makedirs(inbox_dir)
        inbox_file = os.path.join(inbox_dir, "inbox.json")
        with open(inbox_file, "w") as f:
            json.dump({"agent": agent, "messages": [], "has_unread": False}, f)

        mail = {
            "to": "lingzhao+mailbus@example.com",
            "from": "someone <someone@x.com>",
            "subject": "测试邮件",
            "body": "你好",
            "id": "email-002",
        }
        config = {"mail": {"agent_mapping": {
            "lingzhao+mailbus@example.com": "lingzhao"
        }}}
        result = route_email(mail, config, tmp)
        assert result == "lingzhao"

        # 验证写入内容
        inbox = json.load(open(inbox_file))
        assert inbox["has_unread"] is True
        assert len(inbox["messages"]) == 1
        assert "someone@x.com" in inbox["messages"][0]["from"]


def test_route_email_no_dir():
    """inbox 目录不存在时返回 None"""
    with tempfile.TemporaryDirectory() as tmp:
        mail = {"to": "test@example.com", "from": "x@y.com",
                "subject": "Hi", "body": "Hi", "id": "email-003"}
        config = {"mail": {"agent_mapping": {"test@example.com": "nonexistent"}}}
        result = route_email(mail, config, tmp)
        assert result is None


def test_run_once_no_mails():
    """没有 IMAP 配置时返回 0"""
    count = run_once({"mail": {}}, "/tmp")
    assert count == 0


if __name__ == "__main__":
    test_get_password_env()
    print("✅ test_get_password_env")
    test_get_password_fallback()
    print("✅ test_get_password_fallback")
    test_get_password_empty()
    print("✅ test_get_password_empty")
    test_route_email_no_mapping()
    print("✅ test_route_email_no_mapping")
    test_route_email_match()
    print("✅ test_route_email_match")
    test_route_email_no_dir()
    print("✅ test_route_email_no_dir")
    test_run_once_no_mails()
    print("✅ test_run_once_no_mails")
    print("\n🎉 全部通过")
