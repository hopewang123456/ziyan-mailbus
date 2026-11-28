"""MCP 工具面契约守卫：只允许 4 个工具，防止工具面再次膨胀。

对应设计决策：docs/design/agent-unification-design.md §11.3「MCP 工具集（收敛为 4 个）」。
"""

from __future__ import annotations

import json
from pathlib import Path

_CONTRACT = (
    Path(__file__).resolve().parents[3] / "shared" / "contracts" / "mcp-tools-v0.json"
)
_EXPECTED = {"mailbus_inbox", "mailbus_send", "mailbus_ack", "mailbus_result"}


def test_mcp_tool_surface_is_exactly_four_tools():
    data = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    names = [tool["name"] for tool in data["tools"]]
    assert len(names) == 4, f"工具面应恰好 4 个，实际 {names}"
    assert set(names) == _EXPECTED
    assert len(set(names)) == len(names), "工具名不得重复"


def test_every_mcp_tool_has_http_mapping_and_auth():
    data = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    for tool in data["tools"]:
        assert tool.get("http", {}).get("path"), f"{tool['name']} 缺少 http.path"
        assert tool.get("http", {}).get("method") in {"GET", "POST"}, tool["name"]
        assert tool.get("auth") in {"employee_session", "agent_token"}, tool["name"]
