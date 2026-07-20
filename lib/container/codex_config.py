"""生成容器内 ~/.codex/config.toml — 从 render-codex-config.sh 迁出。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

AGENT_DISPLAY = {
    "lingxiao": "灵霄",
    "lingjian": "灵鉴",
}

DEFAULT_MODELS = {
    "lingjian": ("deepseek-reasoner", "medium", "true", "auto"),
    "lingxiao": ("deepseek-v4-flash", "low", "false", "none"),
}


def _identity_paths(agent: str) -> list[str]:
    if agent == "lingxiao":
        return [
            "/mailbus/access/codex/lingxiao/IDENTITY.md",
            "/mailbus/skills/roles/overlays/lingxiao/IDENTITY.md",
            "/mailbus/identities/lingxiao/IDENTITY.md",
            "/mailbus/identities/lingxiao.md",
        ]
    if agent == "lingjian":
        return [
            "/mailbus/access/codex/lingjian/IDENTITY.md",
            "/mailbus/skills/roles/overlays/lingjian/IDENTITY.md",
            "/mailbus/identities/lingjian.md",
        ]
    return [
        f"/mailbus/access/codex/{agent}/IDENTITY.md",
        f"/mailbus/skills/roles/overlays/{agent}/IDENTITY.md",
        f"/mailbus/identities/{agent}.md",
    ]


def _read_identity(agent: str) -> str:
    for path in _identity_paths(agent):
        p = Path(path)
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")[:10000]
    return ""


def _read_memory_block(codex_home: Path, agent: str) -> str:
    memory_file = codex_home / "skills" / f"{agent}-memory" / "output.md"
    if memory_file.is_file():
        return memory_file.read_text(encoding="utf-8", errors="replace")[:6000]
    return ""


def _fetch_agentmemory_snippet(am_url: str, agent: str) -> str:
    wait_script = Path("/usr/local/bin/wait-agentmemory.sh")
    if wait_script.is_file() and os.access(wait_script, os.X_OK):
        subprocess.run([str(wait_script)], check=False, timeout=30)
    url = f"{am_url.rstrip('/')}/agentmemory/memories?agentId={agent}&limit=5&includeOrphans=true"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return ""
    lines: list[str] = []
    for item in (data.get("memories") or [])[:5]:
        content = (item.get("content") or "").replace("\n", " ")[:240]
        if content:
            lines.append(f"- {content}")
    return "\n".join(lines)


def _model_defaults(agent: str) -> tuple[str, str, str, str]:
    return DEFAULT_MODELS.get(agent, ("deepseek-v4-flash", "low", "false", "none"))


def render_codex_config() -> int:
    codex_home = Path(os.environ.get("CODEX_HOME", "/home/node/.codex"))
    agent = os.environ.get("CODEX_AGENT", "lingxiao")
    project_dir = Path(
        os.environ.get(
            "CODEX_PROJECT_DIR",
            f"/home/node/agent-workspace/{agent}",
        )
    )
    gateway_port = os.environ.get("DEEPSEEK_GATEWAY_PORT", "3000")
    am_url = os.environ.get("AGENTMEMORY_URL", "http://iii-engine:3111")
    display = AGENT_DISPLAY.get(agent, agent)
    catalog_src = Path("/usr/local/share/codex/deepseek-model-catalog.json")
    mcp_standalone = Path("/node_modules/@agentmemory/agentmemory/dist/standalone.mjs")
    mcp_enabled = os.environ.get("CODEX_MCP_AGENTMEMORY", "1") == "1"
    team_id = os.environ.get("AGENTMEMORY_TEAM_ID", "ziyan")
    user_id = os.environ.get("AGENTMEMORY_USER_ID", "mailbus")

    default_model, reasoning_effort, supports_reasoning, reasoning_summary = _model_defaults(agent)
    model = os.environ.get("CODEX_MODEL", default_model)
    reasoning_effort = os.environ.get("CODEX_REASONING_EFFORT", reasoning_effort)
    supports_reasoning = os.environ.get("CODEX_SUPPORTS_REASONING", supports_reasoning)
    reasoning_summary = os.environ.get("CODEX_REASONING_SUMMARY", reasoning_summary)

    codex_home.mkdir(parents=True, exist_ok=True)
    if catalog_src.is_file():
        shutil.copy2(catalog_src, codex_home / "deepseek-model-catalog.json")

    instructions = _read_identity(agent)
    memory_block = _read_memory_block(codex_home, agent)
    am_snippet = _fetch_agentmemory_snippet(am_url, agent)

    lines: list[str] = [
        f'model = "{model}"',
        'model_provider = "deepseek-gateway"',
        'model_catalog_json = "deepseek-model-catalog.json"',
        f'model_reasoning_effort = "{reasoning_effort}"',
        f"model_supports_reasoning_summaries = {supports_reasoning}",
        f'model_reasoning_summary = "{reasoning_summary}"',
        'personality = "pragmatic"',
        "",
        "[model_providers.deepseek-gateway]",
        'name = "DeepSeek Gateway"',
        f'base_url = "http://127.0.0.1:{gateway_port}/v1"',
        'wire_api = "responses"',
        "",
    ]

    if instructions or memory_block or am_snippet:
        lines.append('developer_instructions = """')
        if instructions:
            lines.append(instructions)
            lines.append("")
        lines.extend(
            [
                "## 记忆恢复（启动必读）",
                "",
                f"你是 **{agent}（{display}）**。用户期望你带有该角色的历史记忆，不是通用 Codex 助手。",
                f'**禁止**自称 "Codex"、"Codex CLI"、"OpenAI 助手" 或通用 AI 编程助手；必须始终以 {display} 的身份与人设回答。',
                f"若被问「你是谁」，必须回答你是 {display}，不得提及 OpenAI 或 Codex 产品名。",
                "对话开始时，先用 2-4 句话概括下面「本地快照」和「AgentMemory 摘要」中的当前任务/待办，再回答用户问题。",
                f"保存新进展时，用 AgentMemory MCP 或 `python3 {codex_home}/skills/{agent}-memory/save.py`。",
                "",
                f"### 本地快照 ({agent}-memory/output.md)",
            ]
        )
        if memory_block:
            lines.append(memory_block)
            lines.append("")
        else:
            lines.extend(["（暂无本地快照）", ""])
        lines.append("### AgentMemory 近期摘要")
        lines.append(am_snippet if am_snippet else "（暂无远端记忆或未连接 AgentMemory）")
        lines.append('"""')

    if mcp_enabled and mcp_standalone.is_file():
        lines.extend(
            [
                "",
                "[mcp_servers.agentmemory]",
                'command = "node"',
                f'args = ["{mcp_standalone}"]',
                "",
                "[mcp_servers.agentmemory.env]",
                f'AGENTMEMORY_URL = "{am_url}"',
                f'AGENT_ID = "{agent}"',
                f'TEAM_ID = "{team_id}"',
                f'USER_ID = "{user_id}"',
                'AGENTMEMORY_AGENT_SCOPE = "shared"',
                'AGENTMEMORY_FORCE_PROXY = "1"',
            ]
        )
    elif mcp_enabled:
        print(f"[codex-config] agentmemory MCP skipped (missing {mcp_standalone})", file=sys.stderr)

    config_path = codex_home / "config.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    project_codex = project_dir / ".codex"
    project_codex.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, project_codex / "config.toml")
    catalog_dst = codex_home / "deepseek-model-catalog.json"
    if catalog_dst.is_file():
        shutil.copy2(catalog_dst, project_codex / "deepseek-model-catalog.json")

    store_link = project_dir / "store"
    if not store_link.exists():
        os.symlink("/mailbus/store", store_link)

    agents_md = project_dir / "AGENTS.md"
    agents_body = [
        f"# {agent} — Codex 项目指令",
        "",
        f"> Web UI / app-server 会读取本文件。你不是 Codex CLI，你是 **{display}**（agent={agent}）。",
        "",
    ]
    if instructions:
        agents_body.extend([instructions, ""])
    if memory_block:
        agents_body.extend(["## 记忆快照", memory_block])
    agents_md.write_text("\n".join(agents_body) + "\n", encoding="utf-8")

    gateway_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "gateway-local"
    webui = {
        "enabled": True,
        "provider": "custom",
        "customBaseUrl": f"http://127.0.0.1:{gateway_port}/v1",
        "model": model,
        "apiKey": gateway_key,
        "wireApi": "responses",
        "customKey": True,
        "providerKeys": {},
    }
    webui_path = codex_home / "webui-custom-providers.json"
    webui_path.write_text(json.dumps(webui, indent=2) + "\n", encoding="utf-8")

    global_state = {
        "electron-saved-workspace-roots": [str(project_dir)],
        "active-workspace-roots": [str(project_dir)],
        "first-launch-plugins-card-dismissed": True,
    }
    (codex_home / ".codex-global-state.json").write_text(
        json.dumps(global_state, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(webui_path, project_codex / "webui-custom-providers.json")

    sync_mirror = Path("/usr/local/bin/sync-codex-home-mirror.sh")
    if sync_mirror.is_file() and os.access(sync_mirror, os.X_OK):
        subprocess.run([str(sync_mirror)], check=False)

    memory_file = codex_home / "skills" / f"{agent}-memory" / "output.md"
    print(
        f"[codex-config] agent={agent} display={display} model={model} "
        f"reasoning={reasoning_effort}/{reasoning_summary} gateway=127.0.0.1:{gateway_port} "
        f"project={project_dir} memory_file={memory_file} agentmemory={am_url} webui=custom-provider",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    return render_codex_config()


if __name__ == "__main__":
    raise SystemExit(main())
