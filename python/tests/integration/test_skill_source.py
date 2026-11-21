"""L7：技能来源探测不得路径穿越，http 仅允许 http/https。"""

from __future__ import annotations

from mailbus.adapters.system.skill_source import SkillSource
from mailbus.core.skills.values import SkillSourceType


def test_local_entry_cannot_escape_source_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "SKILL.md").write_text("version: 1.0.0\n", encoding="utf-8")
    sub = vault / "nested"
    sub.mkdir()
    (sub / "SKILL.md").write_text("version: 2.0.0\n", encoding="utf-8")
    secret = tmp_path / "SECRET.md"
    secret.write_text("version: leaked\n", encoding="utf-8")

    src = SkillSource()

    # 根目录入口可读
    root_probe = src.probe(SkillSourceType.LOCAL, str(vault), "SKILL.md")
    assert root_probe.reachable
    assert root_probe.version == "1.0.0"

    # 子目录内的合法入口仍可读（不得过度拦截）
    nested = src.probe(SkillSourceType.LOCAL, str(vault), "nested/SKILL.md")
    assert nested.reachable
    assert nested.version == "2.0.0"

    # ../ 穿越到父目录的机密文件不可读
    traversal = src.probe(SkillSourceType.LOCAL, str(vault), "../SECRET.md")
    assert not traversal.reachable

    # 绝对路径入口也被拒
    absolute = src.probe(SkillSourceType.LOCAL, str(vault), str(secret.resolve()))
    assert not absolute.reachable


def test_http_probe_rejects_non_http_schemes():
    src = SkillSource()
    for uri in ["file:///etc/passwd", "ftp://example.com/x", "gopher://h/x"]:
        result = src.probe(SkillSourceType.HTTP, uri, "SKILL.md")
        assert not result.reachable
        assert "http" in (result.error or "")


def test_http_probe_blocks_loopback_and_link_local():
    """L7：阻断本机与链路本地地址，避免 SSRF 探测云元数据或本地服务。"""
    src = SkillSource()
    for uri in [
        "http://127.0.0.1:9/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:9/x",
    ]:
        result = src.probe(SkillSourceType.HTTP, uri, "SKILL.md")
        assert not result.reachable, uri
        assert "不允许" in (result.error or ""), uri
