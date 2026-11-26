#!/usr/bin/env python3
"""为各 openclaw agent 生成独立 OpenClaw 状态目录。

原实现位于已移除的 ``python/lib/adapters/container/openclaw_profiles.py``
（旧 Python 栈于 B7 清理）。容器内 ``/mailbus/python/lib`` 为空目录，
``python3 -m lib.adapters.container.openclaw_profiles`` 会抛
ModuleNotFoundError。此处按新栈位置（``python/tools/``）等价重写，
仅依赖标准库，由 ``init-openclaw-profiles.sh`` 直接调用。

语义保持不变：
  - 模板 = ``<data>/.openclaw/openclaw.json``
  - 为 agent-m / agent-l 生成 ``<data>/.openclaw-<profile>/openclaw.json``
  - 目标文件已存在则跳过（禁止启动时静默覆盖）
  - gateway.port / bind / auth 按 profile 注入
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROFILE_PORTS = {
    "agent-m": 18789,
    "agent-l": 18790,
}


def _workspace_base() -> str:
    # 与原 lib 版一致：读 OPENCLAW_WORKSPACE，未配置则为空串
    return os.environ.get("OPENCLAW_WORKSPACE", "")


def _workspaces() -> dict[str, str]:
    base = _workspace_base()
    return {
        "agent-m": base,
        "agent-l": os.path.join(base, "a-agent-l"),
    }


def _init_profile(profile: str, port: int, statedir: Path, src: Path) -> None:
    statedir.mkdir(parents=True, exist_ok=True)
    out = statedir / "openclaw.json"
    # 已有原生配置则跳过，禁止启动时静默覆盖
    if out.is_file():
        print(f"  skip {profile} -> {out} (exists)")
        return

    cfg = json.loads(src.read_text(encoding="utf-8"))
    cfg.setdefault("gateway", {})
    cfg["gateway"]["port"] = port
    cfg["gateway"]["bind"] = "auto"
    token = (os.environ.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    if token == "change-me":
        token = ""
    if not token:
        print(f"  skip {profile} auth token (set OPENCLAW_GATEWAY_TOKEN)", file=sys.stderr)
    else:
        cfg["gateway"]["auth"] = {"mode": "token", "token": token}

    agents = (cfg.get("agents") or {}).get("list") or []
    picked = [a for a in agents if a.get("id") == profile]
    if not picked:
        picked = [
            {
                "id": profile,
                "workspace": _workspaces().get(profile, os.path.join(_workspace_base(), profile)),
                "model": {"primary": "deepseek/deepseek-chat"},
            }
        ]
    cfg.setdefault("agents", {})["list"] = picked

    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  init {profile} -> {out} (port {port})")


def init_openclaw_profiles(base: str | None = None) -> int:
    base_path = Path(base or os.environ.get("OPENCLAW_DATA_BASE", "/workspace/data"))
    src = base_path / ".openclaw" / "openclaw.json"
    if not src.is_file():
        print(f"[init-openclaw-profiles] missing {src}", file=sys.stderr)
        return 1

    for profile, port in PROFILE_PORTS.items():
        statedir = base_path / f".openclaw-{profile}"
        _init_profile(profile, port, statedir, src)
    return 0


def main() -> int:
    return init_openclaw_profiles()


if __name__ == "__main__":
    raise SystemExit(main())
