#!/usr/bin/env python3
"""同步 Claude Code 人设、skills 与 memory 快照到 claude_home / 项目目录。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.constants import MAILBUS_ROOT
from lib.claude_launch import (
    ensure_claude_agent_settings,
    load_mailbus_claude,
    resolve_claude_home,
    resolve_claude_plat_cfg,
    resolve_claude_workspace,
    resolve_project_dir,
)
from lib.framework_skills import framework_skill_id, sync_agent_skills_from_index
from lib.agent_registry import get_agent
from lib.agentmemory_config import agentmemory_url
from lib.sync_layers import default_use_symlink, normalize_host_path
from lib.utils import identity_candidates, json_read

MAIL_ROOT = MAILBUS_ROOT


def _ai_tools_root() -> Path:
    return Path(ROOT).parent


def _resolve_path(rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/")
    if not rel:
        raise ValueError("empty path")
    if rel.startswith(".codex/"):
        return _ai_tools_root() / rel
    if rel.startswith("mailbus-core/") or rel.startswith("team-pack/"):
        return normalize_host_path(rel, mail_root=Path(ROOT))
    if rel.startswith("mail/"):
        return normalize_host_path(rel, mail_root=Path(ROOT))
    if rel.startswith("store/"):
        return Path(ROOT) / rel.replace("store/", "", 1)
    p = Path(rel)
    if p.is_absolute():
        return normalize_host_path(rel, mail_root=Path(ROOT))
    return _ai_tools_root() / rel


def _load_skills_index(data_dir: str) -> dict:
    path = Path(data_dir) / "agents" / "json" / "skills-index.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_identity(data_dir: str, agent: str, agent_cfg: dict) -> str:
    paths = agent_cfg.get("profile_paths") or {}
    configured = paths.get("identity") or ""
    for p in identity_candidates(data_dir, agent, configured):
        if os.path.isfile(p):
            return Path(p).read_text(encoding="utf-8")[:12000]
    return ""


def _fetch_agentmemory_snippet(agent: str, limit: int = 5) -> str:
    base = agentmemory_url().rstrip("/")
    url = f"{base}/agentmemory/memories?agentId={agent}&limit={limit}&includeOrphans=true"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return ""
    lines = []
    for m in (data.get("memories") or [])[:limit]:
        c = (m.get("content") or "").replace("\n", " ")[:240]
        if c:
            lines.append(f"- {c}")
    return "\n".join(lines)


def _write_memory_skill(skills_dir: Path, agent: str, identity: str, am_snippet: str) -> None:
    mem_dir = skills_dir / f"{agent}-memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    skill_md = mem_dir / "SKILL.md"
    if not skill_md.is_file():
        skill_md.write_text(
            f"# {agent} memory\n\n"
            "本地记忆快照。启动 Web/CLI 前由 mailbus sync-claude-agent-context 刷新 `output.md`。\n",
            encoding="utf-8",
        )
    parts = ["# 记忆快照", ""]
    if identity:
        parts.extend(["## 身份摘要", identity[:4000], ""])
    if am_snippet:
        parts.extend(["## AgentMemory 近期", am_snippet, ""])
    if len(parts) <= 2:
        parts.append("（暂无记忆）")
    (mem_dir / "output.md").write_text("\n".join(parts).strip() + "\n", encoding="utf-8")


def _sync_skills_from_index(
    skills_dir: Path,
    agent: str,
    index: dict,
    *,
    link_codex_skills: bool = True,
) -> None:
    skills_dir.mkdir(parents=True, exist_ok=True)
    sync_agent_skills_from_index(
        agent,
        skills_dir,
        index,
        mail_root=Path(ROOT),
        use_symlink=link_codex_skills and default_use_symlink(),
    )


def _neutralize_repo_claude_md(push_cwd: Path) -> None:
    """仓库根 CLAUDE.md 若含单一 agent 人设，改为中性说明，避免子目录会话继承灵云。"""
    repo_md = push_cwd / "CLAUDE.md"
    if not repo_md.is_file():
        return
    try:
        text = repo_md.read_text(encoding="utf-8")
    except OSError:
        return
    if "灵云" in text or ("mailbus agent:" in text and "lingyun" in text):
        repo_md.write_text(
            "# ai_tools\n\n"
            "本仓库根目录**无单一 agent 人设**。Claude Code 请进入各 agent 独立工作区：\n\n"
            "- 灵云 `lingyun` → `.mailbus/claude/lingyun/`\n"
            "- 灵验 `lingyan` → `.mailbus/claude/lingyan/`\n\n"
            "不要在根目录启动 Claude Code 会话。\n",
            encoding="utf-8",
        )


def sync_agent(agent: str, data_dir: str) -> dict:
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent not in agents:
        raise ValueError(f"unknown agent: {agent}")
    agent_cfg = agents[agent]

    global_cfg = load_mailbus_claude(data_dir)
    _, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    ensure_claude_agent_settings(agent, data_dir)
    claude_home = Path(resolve_claude_home(plat_cfg, agent))
    access_rec = get_agent(agent) or {}
    ws = access_rec.get("workspace")
    if ws:
        project_dir = normalize_host_path(str(ws), mail_root=Path(ROOT))
    else:
        project_dir = Path(resolve_claude_workspace(agent_cfg, plat_cfg, agent))
    push_cwd = Path(resolve_project_dir(agent_cfg, plat_cfg, agent))
    skills_dir = claude_home / "skills"
    index = _load_skills_index(data_dir)
    identity = _load_identity(data_dir, agent, agent_cfg)
    am_snippet = _fetch_agentmemory_snippet(agent)

    _sync_skills_from_index(skills_dir, agent, index)
    _write_memory_skill(skills_dir, agent, identity, am_snippet)

    claude_md_parts = [
        f"# {agent_cfg.get('name', agent)} — Claude Code 项目上下文",
        "",
        f"> mailbus agent: **{agent}** · push cwd: `{push_cwd}`",
        "> 由 mailbus sync-claude-agent-context 生成，勿手改后指望持久（会被覆盖）。",
        "",
    ]
    if identity:
        claude_md_parts.extend([identity, ""])
    if am_snippet:
        claude_md_parts.extend(["## AgentMemory 近期", am_snippet, ""])
    claude_md = "\n".join(claude_md_parts).strip() + "\n"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    _neutralize_repo_claude_md(push_cwd)

    return {
        "agent": agent,
        "claude_home": str(claude_home),
        "project_dir": str(project_dir),
        "push_cwd": str(push_cwd),
        "skills_dir": str(skills_dir),
        "platform": resolve_claude_plat_cfg(global_cfg)[0],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("agent")
    p.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or os.path.join(ROOT, "store"))
    args = p.parse_args()
    try:
        info = sync_agent(args.agent, args.data_dir)
        print(json.dumps(info, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
