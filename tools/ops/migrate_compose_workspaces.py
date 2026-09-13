#!/usr/bin/env python3
"""Migrate compose framework workspaces into docker-agents/workspaces/.

Reads current paths from docker-agents/.env (OPENCLAW_WORKSPACE, CODEX_*, …),
links or copies them under workspaces/, then rewrites .env to mailbus-local paths.

Does not guess ai_tools/Agent layout — source = whatever .env already points to
(or --from-dir / explicit --map).

Examples:
  python tools/ops/migrate_compose_workspaces.py --dry-run
  python tools/ops/migrate_compose_workspaces.py --link --update-env
  python tools/ops/migrate_compose_workspaces.py --copy --update-env
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAILBUS_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = MAILBUS_ROOT / "docker-agents"
WORKSPACES = COMPOSE_DIR / "workspaces"
ENV_PATH = COMPOSE_DIR / ".env"

# env key → destination folder name under workspaces/
WORKSPACE_KEYS: dict[str, str] = {
    "OPENCLAW_WORKSPACE": "openclaw",
    "CODEX_WORKSPACE": "codex",
    "CODEX_REVIEW_WORKSPACE": "codex-review",
    "OPENCODE_ROOT": "opencode",
    "DSH_WORKSPACE": "dsh",
    "HERMES_DATA": "hermes-data",
}


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _wsl_to_win(p: str) -> Path:
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", p.replace("\\", "/"))
    if m:
        return Path(f"{m.group(1).upper()}:/") / m.group(2).replace("/", "\\")
    return Path(p)


def _win_to_wsl(p: Path) -> str:
    s = str(p.resolve())
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
    if m:
        return "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")
    return s.replace("\\", "/")


def _link(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        # Directory junction — no admin required
        subprocess.check_call(["cmd", "/c", "mklink", "/J", str(dst), str(src)], shell=False)
    else:
        os.symlink(src, dst, target_is_directory=True)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        raise FileExistsError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True)


def _rewrite_env(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    keys_done: set[str] = set()
    out: list[str] = []
    for line in lines:
        raw = line
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, _ = s.partition("=")
            k = k.strip()
            if k in updates:
                nl = "\n" if line.endswith("\n") else ""
                out.append(f"{k}={updates[k]}{nl}")
                keys_done.add(k)
                continue
        out.append(raw)
    for k, v in updates.items():
        if k not in keys_done:
            out.append(f"{k}={v}\n")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--link", action="store_true", help="junction/symlink (default if neither --copy)")
    ap.add_argument("--copy", action="store_true", help="full copy instead of link")
    ap.add_argument("--update-env", action="store_true", help="rewrite docker-agents/.env to workspaces paths")
    ap.add_argument(
        "--host-root",
        default="",
        help="WSL/Docker host root for .env values (default: MAILBUS_HOST_ROOT from .env or /mnt/.../mailbus)",
    )
    ap.add_argument(
        "--only",
        default="",
        help="comma-separated env keys to migrate (default: all set keys)",
    )
    args = ap.parse_args()
    mode_copy = bool(args.copy)
    if not args.copy and not args.link:
        args.link = True

    env = _load_env(ENV_PATH)
    host_root = (args.host_root or env.get("MAILBUS_HOST_ROOT") or "").strip()
    if not host_root:
        host_root = _win_to_wsl(MAILBUS_ROOT)

    only = {x.strip() for x in args.only.split(",") if x.strip()} or set(WORKSPACE_KEYS)

    plans: list[tuple[str, Path, Path, str]] = []
    for key, folder in WORKSPACE_KEYS.items():
        if key not in only:
            continue
        src_raw = (env.get(key) or "").strip()
        if not src_raw:
            print(f"skip {key}: empty in .env")
            continue
        src = _wsl_to_win(src_raw)
        dst = WORKSPACES / folder
        new_val = f"{host_root.rstrip('/')}/docker-agents/workspaces/{folder}"
        # Already under workspaces?
        try:
            if src.resolve() == dst.resolve():
                print(f"ok {key}: already at {dst}")
                continue
        except OSError:
            pass
        if "docker-agents/workspaces/" in src_raw.replace("\\", "/"):
            print(f"ok {key}: already workspace-relative ({src_raw})")
            continue
        plans.append((key, src, dst, new_val))

    if not plans:
        print("nothing to migrate")
        return 0

    updates: dict[str, str] = {}
    for key, src, dst, new_val in plans:
        print(f"{'[dry] ' if args.dry_run else ''}{key}: {src} -> {dst} ({'copy' if mode_copy else 'link'})")
        if not src.exists():
            print(f"  WARN: source missing — create empty dest only", file=sys.stderr)
            if not args.dry_run:
                dst.mkdir(parents=True, exist_ok=True)
            updates[key] = new_val
            continue
        if args.dry_run:
            updates[key] = new_val
            continue
        if dst.exists() or dst.is_symlink():
            print(f"  skip: dest exists {dst}", file=sys.stderr)
            updates[key] = new_val
            continue
        if mode_copy:
            _copy_tree(src, dst)
        else:
            _link(src, dst)
        updates[key] = new_val

    if args.update_env and updates:
        if not ENV_PATH.is_file():
            print("no .env to update", file=sys.stderr)
            return 1
        text = ENV_PATH.read_text(encoding="utf-8")
        new_text = _rewrite_env(text, updates)
        print(f"{'[dry] ' if args.dry_run else ''}update {ENV_PATH}")
        if not args.dry_run:
            ENV_PATH.write_text(new_text, encoding="utf-8")

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
