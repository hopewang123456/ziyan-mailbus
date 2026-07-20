"""目标机：解压 bundle + write_env + rewrite + init/sync 链。"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from pathlib import Path

from paths import load_mailbus_env_keys, to_wsl_path
from rewrite_paths import rewrite_tree
from write_env import write_env


def _resolve_mailbus_root(prefix: Path) -> Path:
    for candidate in (prefix / "mailbus-core", prefix / "mail", Path(__file__).resolve().parent.parent):
        if (candidate / "tools" / "mailbus.py").is_file():
            return candidate.resolve()
    return (prefix / "mailbus-core").resolve()


def _import_env(prefix: Path, root: Path, env_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("'\"")
            if key and val:
                env[key] = val
    load_mailbus_env_keys()
    env.update({k: v for k, v in os.environ.items() if k.startswith("MAILBUS_") or k in (
        "OPENCLAW_WORKSPACE", "OPENCODE_ROOT", "NODE_MODULES", "HERMES_DATA", "TEAM_PACK_ROOT",
        "LINGXIAO_WORKSPACE", "COMPOSE_PROJECT_NAME",
    )})
    env["MAILBUS_ROOT"] = to_wsl_path(root)
    data = env.get("MAILBUS_DATA") or to_wsl_path(prefix / "mail" / "store")
    env["MAILBUS_DATA"] = data
    return env


def import_bundle(
    bundle: Path,
    install_prefix: Path,
    *,
    dry_run: bool = False,
    skip_post: bool = False,
) -> int:
    prefix = install_prefix.resolve()
    prefix.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"[import] would extract {bundle} -> {prefix}")
        return 0

    with tarfile.open(bundle, "r:gz") as tar:
        tar.extractall(prefix)

    env_path = write_env(prefix)
    print(f"[import] wrote {env_path}")

    stats = rewrite_tree(prefix, dry_run=False)
    print(f"[import] rewrite files={stats['files']} replacements={stats['replacements']}")

    if skip_post:
        return 0

    root = _resolve_mailbus_root(prefix)
    env = _import_env(prefix, root, env_path)
    py = sys.executable
    steps = [
        ([py, str(root / "tools" / "init-store.py")], "init-store", True),
        ([py, str(root / "tools" / "sync-all-agent-layers.py")], "sync-all", True),
        ([py, str(root / "tools" / "mailbus.py"), "compose", "sync"], "compose-sync", True),
        ([py, str(root / "tools" / "mailbus.py"), "doctor"], "doctor", False),
    ]
    exit_code = 0
    for cmd, label, strict in steps:
        print(f"[import] running {label}...")
        r = subprocess.run(cmd, cwd=str(root), env=env)
        if r.returncode != 0:
            if strict:
                print(f"[import] FAIL: {label} exit {r.returncode}", file=sys.stderr)
                exit_code = r.returncode
            else:
                print(f"[import] WARN: {label} exit {r.returncode}", file=sys.stderr)
    return exit_code


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Import mailbus migrate bundle")
    ap.add_argument("bundle")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-post", action="store_true")
    args = ap.parse_args()
    return import_bundle(Path(args.bundle), Path(args.prefix), dry_run=args.dry_run, skip_post=args.skip_post)


if __name__ == "__main__":
    raise SystemExit(main())
