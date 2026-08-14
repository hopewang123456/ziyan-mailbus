#!/usr/bin/env python3
"""同步 Codex Desktop / CLI 的 config.toml + 模型目录（消除 deepseek metadata 警告 + 注入 agent 人设）。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.infra.utils import identity_candidates

CATALOG_SRC = os.path.join(ROOT, "docker-agents", "codex-agent", "deepseek-model-catalog.json")
CATALOG_NAME = "deepseek-model-catalog.json"

AGENT_GATEWAY_PORTS = {
    "agent-g": 9220,
    "agent-e": 9221,
}

AGENT_DEFAULTS: dict[str, dict[str, str | bool]] = {
    "agent-g": {
        "model": "deepseek-v4-flash",
        "reasoning_effort": "low",
        "supports_reasoning_summaries": False,
        "reasoning_summary": "none",
    },
    "agent-e": {
        "model": "deepseek-reasoner",
        "reasoning_effort": "medium",
        "supports_reasoning_summaries": True,
        "reasoning_summary": "auto",
    },
}


def resolve_codex_home(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    for cand in (
        os.environ.get("CODEX_HOME"),
        r"E:\.codex",
        os.path.join(os.path.expanduser("~"), ".codex"),
    ):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    home = os.path.join(os.path.expanduser("~"), ".codex")
    os.makedirs(home, exist_ok=True)
    return home


def load_identity(data_dir: str, agent: str, agent_cfg: dict) -> str:
    paths = agent_cfg.get("profile_paths") or {}
    configured = paths.get("identity") or ""
    for p in identity_candidates(data_dir, agent, configured):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return f.read()[:12000]
    return ""


def agent_reasoning_profile(agent: str, agent_cfg: dict) -> dict[str, str | bool]:
    defaults = dict(AGENT_DEFAULTS.get(agent, AGENT_DEFAULTS["agent-g"]))
    model = agent_cfg.get("model") or defaults["model"]
    defaults["model"] = model
    if model == "deepseek-reasoner":
        defaults["reasoning_effort"] = "medium"
        defaults["supports_reasoning_summaries"] = True
        defaults["reasoning_summary"] = "auto"
    return defaults


def render_config_toml(
    *,
    model: str,
    gateway_port: int,
    instructions: str,
    reasoning_effort: str,
    supports_reasoning_summaries: bool,
    reasoning_summary: str,
) -> str:
    lines = [
        f'model = "{model}"',
        'model_provider = "deepseek-gateway"',
        'model_catalog_json = "deepseek-model-catalog.json"',
        f'model_reasoning_effort = "{reasoning_effort}"',
        f"model_supports_reasoning_summaries = {str(supports_reasoning_summaries).lower()}",
        f'model_reasoning_summary = "{reasoning_summary}"',
        'personality = "pragmatic"',
        "",
        "[model_providers.deepseek-gateway]",
        'name = "DeepSeek Gateway"',
        f'base_url = "http://127.0.0.1:{gateway_port}/v1"',
        'wire_api = "responses"',
        "",
    ]
    if instructions.strip():
        lines.extend(
            [
                'developer_instructions = """',
                instructions.rstrip(),
                '"""',
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 Codex Desktop 配置")
    ap.add_argument("agent", help="agent key，如 agent-g / agent-e")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--codex-home", default=None)
    ap.add_argument("--gateway-port", type=int, default=None)
    args = ap.parse_args()

    config_path = os.path.join(os.path.abspath(args.data_dir), "config.json")
    if not os.path.isfile(config_path):
        print(f"ERROR: missing {config_path}", file=sys.stderr)
        return 2

    cfg = json.load(open(config_path, encoding="utf-8"))
    agent_cfg = (cfg.get("agents") or {}).get(args.agent)
    if not agent_cfg:
        print(f"ERROR: unknown agent {args.agent}", file=sys.stderr)
        return 2

    codex_home = resolve_codex_home(args.codex_home)
    os.makedirs(codex_home, exist_ok=True)

    if not os.path.isfile(CATALOG_SRC):
        print(f"ERROR: missing catalog {CATALOG_SRC}", file=sys.stderr)
        return 2
    shutil.copy2(CATALOG_SRC, os.path.join(codex_home, CATALOG_NAME))

    profile = agent_reasoning_profile(args.agent, agent_cfg)
    gateway_port = args.gateway_port or AGENT_GATEWAY_PORTS.get(args.agent, 9220)
    instructions = load_identity(os.path.abspath(args.data_dir), args.agent, agent_cfg)
    toml_path = os.path.join(codex_home, "config.toml")
    force = os.environ.get("FORCE_RENDER_CODEX_CONFIG", "0") == "1"
    if os.path.isfile(toml_path) and not force:
        print(
            f"SKIP existing {toml_path} (set FORCE_RENDER_CODEX_CONFIG=1 to overwrite) "
            f"agent={args.agent} gateway=127.0.0.1:{gateway_port}"
        )
        return 0
    with open(toml_path, "w", encoding="utf-8") as f:
        f.write(
            render_config_toml(
                model=str(profile["model"]),
                gateway_port=gateway_port,
                instructions=instructions,
                reasoning_effort=str(profile["reasoning_effort"]),
                supports_reasoning_summaries=bool(profile["supports_reasoning_summaries"]),
                reasoning_summary=str(profile["reasoning_summary"]),
            )
        )

    print(
        f"OK codex_home={codex_home} agent={args.agent} model={profile['model']} "
        f"reasoning={profile['reasoning_effort']}/{profile['reasoning_summary']} "
        f"gateway=127.0.0.1:{gateway_port}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
