#!/usr/bin/env python3
"""同步 lingxiao 容器 Cline openai-compatible → DeepSeek（修复过期 providers.json / .env）。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAIL = Path(__file__).resolve().parent.parent
CONTAINER = os.environ.get("MAILBUS_CONTAINER_LINGXIAO", "docker-agents-lingxiao-1")
PROVIDERS = "/root/.cline/data/settings/providers.json"
HERMES_ENV = Path(os.environ.get("HERMES_ENV", "/mnt/e/hermes-data/.hermes/.env"))
DOCKER_ENV = MAIL / "docker-agents" / ".env"
COMPOSE_DIR = MAIL / "docker-agents"


def _run(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=cwd)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip("'\"")
    return out


def _write_env_kv(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pat = re.compile(rf"^{re.escape(key)}=")
    replaced = False
    new_lines = []
    for line in lines:
        if pat.match(line):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def sync_docker_env_from_hermes() -> bool:
    """把 docker-agents/.env 的 DEEPSEEK/OPENAI key 与 Hermes 对齐。"""
    hermes = _parse_env_file(HERMES_ENV)
    key = hermes.get("DEEPSEEK_API_KEY") or hermes.get("OPENAI_API_KEY")
    if not key:
        print(f"✗ Hermes env 无 DEEPSEEK_API_KEY: {HERMES_ENV}", file=sys.stderr)
        return False
    DOCKER_ENV.parent.mkdir(parents=True, exist_ok=True)
    if not DOCKER_ENV.is_file():
        DOCKER_ENV.write_text("# synced from hermes\n", encoding="utf-8")
    _write_env_kv(DOCKER_ENV, "DEEPSEEK_API_KEY", key)
    _write_env_kv(DOCKER_ENV, "OPENAI_API_KEY", key)
    print(f"✓ 已同步 {DOCKER_ENV.name} ← Hermes DEEPSEEK_API_KEY")
    return True


def recreate_dali() -> int:
    if not COMPOSE_DIR.is_dir():
        return 1
    r = _run(
        ["docker", "compose", "up", "-d", "--build", "--force-recreate", "dali"],
        check=False,
        cwd=COMPOSE_DIR,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    print("✓ dali 容器已重建")
    return 0


def recreate_lingxiao() -> int:
    if not COMPOSE_DIR.is_dir():
        print(f"✗ 缺少 compose 目录: {COMPOSE_DIR}", file=sys.stderr)
        return 1
    r = _run(
        ["docker", "compose", "up", "-d", "--build", "--force-recreate", "lingxiao"],
        check=False,
        cwd=COMPOSE_DIR,
    )
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        return r.returncode
    print("✓ lingxiao 容器已重建")
    return 0


def _container_env(name: str) -> str:
    r = _run(["docker", "exec", CONTAINER, "printenv", name], check=False)
    return (r.stdout or "").strip()


def _redact_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "***"
    return key[:6] + "..." + key[-4:]


def _resolve_api_key() -> tuple[str, str]:
    key = _container_env("DEEPSEEK_API_KEY") or _container_env("OPENAI_API_KEY")
    source = "container"
    if not key:
        hermes = _parse_env_file(HERMES_ENV)
        key = hermes.get("DEEPSEEK_API_KEY") or hermes.get("OPENAI_API_KEY") or ""
        source = "hermes-file"
    return key, source


def sync_cline_auth(*, dry_run: bool = False) -> int:
    api_key, source = _resolve_api_key()
    base_url = _container_env("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.environ.get("CLINE_MODEL", "deepseek-chat")

    if not api_key:
        print(f"✗ 无可用 API key（container / {HERMES_ENV}）", file=sys.stderr)
        return 1

    print(f"容器: {CONTAINER}")
    print(f"Key 来源: {source} → {_redact_key(api_key)}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")

    if dry_run:
        print("(dry-run) 跳过 cline auth")
        return 0

    cmd = [
        "docker", "exec", CONTAINER,
        "cline", "auth", "openai-compatible",
        "-k", api_key,
        "-b", base_url,
        "-m", model,
    ]
    r = _run(cmd, check=False)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        print("✗ cline auth 失败", file=sys.stderr)
        return r.returncode

    r2 = _run(["docker", "exec", CONTAINER, "cat", PROVIDERS], check=False)
    if r2.returncode == 0 and r2.stdout.strip():
        print("✓ providers.json 已更新")
    else:
        print("✓ cline auth 完成")
    return 0


def smoke_test(*, timeout: int = 25) -> int:
    api_key, _ = _resolve_api_key()
    if not api_key:
        return 1
    inner = (
        f"cline 'Reply with exactly: OK' -P openai-compatible -m deepseek-chat "
        f"-k '{api_key}' -t {timeout} -c /mailbus/store --json"
    )
    r = _run(["docker", "exec", CONTAINER, "bash", "-lc", inner], check=False)
    out = (r.stdout or "") + (r.stderr or "")
    if "Incorrect API key" in out:
        print("✗ smoke test 失败: API key 无效")
        print(out[:500])
        return 1
    if r.returncode != 0 and "OK" not in out:
        print("✗ smoke test 失败:")
        print(out[:800])
        return 1
    print("✓ smoke test 通过")
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Fix Cline DeepSeek auth in lingxiao container")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync-env", action="store_true", help="docker-agents/.env ← Hermes")
    ap.add_argument("--recreate", action="store_true", help="重建 lingxiao 容器")
    ap.add_argument("--smoke", action="store_true", help="auth 后短 prompt 验证")
    ap.add_argument("--smoke-only", action="store_true")
    ap.add_argument("--all", action="store_true", help="sync-env + recreate + auth + smoke")
    args = ap.parse_args()

    if args.all:
        args.sync_env = args.recreate = args.smoke = True

    if args.smoke_only:
        return smoke_test()

    if args.sync_env and not sync_docker_env_from_hermes():
        return 1
    if args.recreate:
        rc = recreate_lingxiao()
        if rc != 0:
            return rc

    rc = sync_cline_auth(dry_run=args.dry_run)
    if rc != 0:
        return rc
    if args.smoke:
        return smoke_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
