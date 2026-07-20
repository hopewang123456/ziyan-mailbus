#!/usr/bin/env python3
"""批量部署 Quality Harness post-commit hook 到多个 git 仓库。

用法:
  python tools/harness/deploy-hooks.py --projects /path/a /path/b
  python tools/harness/deploy-hooks.py --manifest config/mailbus/harness-projects.example.json
  python tools/harness/deploy-hooks.py --manifest projects.json --publish --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAIL_ROOT = Path(__file__).resolve().parents[2]
INSTALL_HOOK = MAIL_ROOT / "tools" / "harness" / "install-hook.py"


@dataclass(frozen=True)
class ProjectTarget:
    repo: Path
    publish: bool
    name: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.repo.name


def _posix(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _resolve_repo(raw: str | Path, base: Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def _parse_project_entry(
    entry: str | dict,
    *,
    base: Path,
    default_publish: bool,
) -> ProjectTarget:
    if isinstance(entry, str):
        repo = _resolve_repo(entry, base)
        return ProjectTarget(repo=repo, publish=default_publish)

    if not isinstance(entry, dict):
        raise ValueError(f"invalid project entry: {entry!r}")

    raw_repo = entry.get("repo") or entry.get("path")
    if not raw_repo:
        raise ValueError(f"project entry missing repo/path: {entry!r}")

    publish = entry.get("publish", default_publish)
    if not isinstance(publish, bool):
        raise ValueError(f"project publish must be bool: {entry!r}")

    return ProjectTarget(
        repo=_resolve_repo(raw_repo, base),
        publish=publish,
        name=entry.get("name"),
    )


def load_manifest(manifest_path: Path) -> tuple[Path, list[ProjectTarget]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a JSON object")

    base = manifest_path.parent.resolve()
    mailbus_raw = data.get("mailbus_root")
    mailbus_root = _resolve_repo(mailbus_raw, base) if mailbus_raw else MAIL_ROOT

    default_publish = bool(data.get("publish", False))
    projects_raw = data.get("projects")
    if not isinstance(projects_raw, list) or not projects_raw:
        raise ValueError("manifest must contain a non-empty projects array")

    targets = [_parse_project_entry(item, base=base, default_publish=default_publish) for item in projects_raw]
    return mailbus_root, targets


def collect_targets(args: argparse.Namespace) -> tuple[Path, list[ProjectTarget]]:
    mailbus_root = args.mailbus_root.resolve()
    default_publish = bool(args.publish)

    if args.manifest:
        manifest_path = args.manifest.resolve()
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest not found: {manifest_path}")
        mb, targets = load_manifest(manifest_path)
        if args.mailbus_root != MAIL_ROOT:
            mailbus_root = args.mailbus_root.resolve()
        else:
            mailbus_root = mb
        if args.publish:
            targets = [ProjectTarget(t.repo, True, t.name) for t in targets]
        return mailbus_root, targets

    if not args.projects:
        raise ValueError("provide --projects and/or --manifest")

    targets = [
        ProjectTarget(repo=_resolve_repo(p, Path.cwd()), publish=default_publish)
        for p in args.projects
    ]
    return mailbus_root, targets


def validate_repo(repo: Path) -> str | None:
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        return f"not a git repo: {repo}"
    return None


def install_one(
    target: ProjectTarget,
    *,
    mailbus_root: Path,
    dry_run: bool,
) -> int:
    err = validate_repo(target.repo)
    if err:
        print(f"ERROR [{target.label}]: {err}", file=sys.stderr)
        return 2

    publish = "on" if target.publish else "dry-run"
    print(f"{'[dry-run] ' if dry_run else ''}{target.label}: repo={_posix(target.repo)} publish={publish}")

    if dry_run:
        return 0

    if not INSTALL_HOOK.is_file():
        print(f"ERROR: install-hook missing: {INSTALL_HOOK}", file=sys.stderr)
        return 2

    cmd = [
        sys.executable,
        str(INSTALL_HOOK),
        "--repo",
        str(target.repo),
        "--mailbus-root",
        str(mailbus_root),
    ]
    if target.publish:
        cmd.append("--publish")

    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        return proc.returncode
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy mailbus post-commit harness hooks to multiple repos")
    ap.add_argument(
        "--projects",
        nargs="+",
        type=Path,
        help="git repository paths (absolute or relative to cwd)",
    )
    ap.add_argument(
        "--manifest",
        type=Path,
        help="JSON manifest with projects list (see config/mailbus/harness-projects.example.json)",
    )
    ap.add_argument(
        "--mailbus-root",
        type=Path,
        default=MAIL_ROOT,
        help="mailbus checkout used by installed hooks",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="enable real POST (MAILBUS_PUBLISH=1) for all targets",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="validate repos and print plan without writing hooks",
    )
    args = ap.parse_args()

    if not args.manifest and not args.projects:
        ap.error("at least one of --projects or --manifest is required")

    try:
        mailbus_root, targets = collect_targets(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"mailbus_root={_posix(mailbus_root)}")
    print(f"targets={len(targets)}")

    rc = 0
    for target in targets:
        code = install_one(target, mailbus_root=mailbus_root, dry_run=args.dry_run)
        if code != 0:
            rc = code
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
