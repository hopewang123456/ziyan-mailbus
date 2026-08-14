"""批量替换 store/transport/.sync 中的旧绝对路径前缀。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from paths import MAILBUS_CORE, collect_old_prefixes, to_wsl_path


def _replace_in_string(text: str, old_prefixes: list[str], new_prefix: str) -> tuple[str, int]:
    count = 0
    out = text
    for old in old_prefixes:
        if not old:
            continue
        variants = {old, old.replace("/", "\\"), old.replace("\\", "/")}
        for v in variants:
            if v in out:
                n = out.count(v)
                out = out.replace(v, new_prefix)
                count += n
    return out, count


def rewrite_tree(
    install_prefix: Path,
    *,
    mailbus_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    root = (mailbus_root or install_prefix / "mailbus-core").resolve()
    if not (root / "tools" / "mailbus.py").is_file():
        alt = (install_prefix / "mail").resolve()
        if (alt / "tools" / "mailbus.py").is_file():
            root = alt
    new_prefix = to_wsl_path(install_prefix)
    old_prefixes = collect_old_prefixes(install_prefix)
    stats: dict[str, int] = {"files": 0, "replacements": 0}

    scan_roots = [
        root / "store",
        root / "access" / "transport",
        root / "access" / "hermes" / ".sync",
        root / "config",
        install_prefix / ".mailbus",
    ]
    suffixes = (".json", ".md", ".yaml", ".yml", ".toml", ".txt", ".env")
    for base in scan_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in suffixes:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new_text, n = _replace_in_string(raw, old_prefixes, new_prefix)
            if n == 0 and path.name != "base.json":
                continue
            if path.name == "base.json" and '"canonical_root"' in raw:
                try:
                    data = json.loads(raw)
                    data["canonical_root"] = new_prefix
                    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                    n = 1
                except json.JSONDecodeError:
                    pass
            if n == 0:
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path.name
            stats["files"] += 1
            stats["replacements"] += n
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")
            print(f"  rewrite {rel} ({n} replacements)")

    transport_dir = root / "access" / "transport"
    if transport_dir.is_dir() and not dry_run:
        _rewrite_transport_workspaces(transport_dir, install_prefix)

    return stats


def _rewrite_transport_workspaces(transport_dir: Path, install_prefix: Path) -> None:
    mapping = {
        "agent-f": install_prefix / "agent-f",
        "opencode": install_prefix / "opencode",
        "openclaw_space": install_prefix / "openclaw_space",
    }
    for agent_dir in transport_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        tj = agent_dir / "transport.json"
        if not tj.is_file():
            continue
        try:
            data = json.loads(tj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ws = data.get("workspace") or ""
        push = data.get("push") or {}
        agent_id = data.get("agent_id") or agent_dir.name
        if agent_id == "agent-f" and mapping["agent-f"].exists():
            data["workspace"] = to_wsl_path(mapping["agent-f"])
        if data.get("framework") == "opencode" and mapping["opencode"].exists():
            data["workspace"] = to_wsl_path(mapping["opencode"])
            push["cwd"] = to_wsl_path(mapping["opencode"])
            data["push"] = push
        if data.get("framework") == "openclaw":
            sub = mapping["openclaw_space"] / ("a-agent-g" if agent_id == "agent-g" else "")
            if agent_id == "agent-g" and sub.exists():
                data["workspace"] = to_wsl_path(sub)
            elif mapping["openclaw_space"].exists():
                data["workspace"] = to_wsl_path(mapping["openclaw_space"])
        if data.get("framework") == "claude_code":
            claude_ws = install_prefix / ".mailbus" / "claude" / agent_id
            if claude_ws.exists() or not ws:
                data["workspace"] = to_wsl_path(claude_ws)
                push["cwd"] = to_wsl_path(claude_ws)
                data["push"] = push
        tj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Rewrite absolute paths after migrate")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = rewrite_tree(Path(args.prefix), dry_run=args.dry_run)
    print(f"[rewrite] files={stats['files']} replacements={stats['replacements']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
