#!/usr/bin/env python3
"""灵鉴 Codex 推送配置补丁：沙箱 + pipeline 模型。

根因：WSL 默认无 user namespace，codex -s workspace-write 内 bwrap 失败。
补丁：push/codex.sandbox → danger-full-access；pipeline 推送用 deepseek-flash。

可选（宿主机 WSL，需 root）：
  echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/99-userns.conf
  sudo sysctl --system
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "store" / "config.json"

PATCH = {
    "push": {
        "cwd": "/mailbus/store",
        "sandbox": "danger-full-access",
        "pipeline_sandbox": "danger-full-access",
        "pipeline_model": "deepseek-flash",
    },
    "codex": {
        "sandbox": "danger-full-access",
        "wsl_userns_hint": (
            "WSL: sysctl kernel.unprivileged_userns_clone=1 "
            "或保持 danger-full-access"
        ),
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    agents = cfg.setdefault("agents", {})
    if "lingjian" not in agents:
        print("lingjian not in config", file=sys.stderr)
        return 1

    lj = agents["lingjian"]
    for key, val in PATCH.items():
        block = lj.setdefault(key, {})
        if isinstance(val, dict):
            block.update(val)
        else:
            lj[key] = val

    if args.dry_run:
        print(json.dumps(lj, ensure_ascii=False, indent=2))
        return 0

    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {CONFIG} → lingjian.push.sandbox=danger-full-access, pipeline_model=deepseek-flash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
