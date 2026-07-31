"""为 xiaoqi / yige 生成独立 OpenClaw 状态目录 — 从 init-openclaw-profiles.sh 迁出。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROFILE_PORTS = {
    "xiaoqi": 18789,
    "yige": 18790,
}


def _openclaw_workspace_base() -> str:
    from ..env_bootstrap import load_mailbus_env, mailbus_paths

    load_mailbus_env()
    return mailbus_paths()["openclaw_workspace"]


def _workspaces() -> dict[str, str]:
    base = _openclaw_workspace_base()
    return {
        "xiaoqi": base,
        "yige": os.path.join(base, "a-yige"),
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
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "ziyan-team")
    cfg["gateway"]["auth"] = {"mode": "token", "token": token}

    agents = (cfg.get("agents") or {}).get("list") or []
    picked = [a for a in agents if a.get("id") == profile]
    if not picked:
        picked = [
            {
                "id": profile,
                "workspace": _workspaces().get(
                    profile,
                    os.path.join(_openclaw_workspace_base(), profile),
                ),
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
