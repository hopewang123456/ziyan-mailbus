#!/usr/bin/env python3
"""Open Hermes/OpenClaw browsers + CLI terminals (no long ensure waits)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from lib.adapters.config.browser_auth import openclaw_gateway_token
from lib.adapters.plane.platform_runner import wsl_exe
from lib.adapters.runtime.cred_delivery import sync_browser_credentials_to_env
from lib.infra.utils import to_wsl_path
from tools.ops.launch_agent import _start_browser

DATA = str(ROOT / "store")


def open_cli(title: str, cmd: str) -> None:
    ts = int(time.time() * 1000)
    win_tmp = Path(tempfile.gettempdir()) / f"mb-cli-{title}-{ts}.sh"
    body = (
        "#!/bin/bash\n"
        "set +e\n"
        f"echo '[mailbus] {title}'\n"
        f"{cmd}\n"
        "echo\n"
        'read -rp "Enter to close..." _\n'
    )
    win_tmp.write_text(body, encoding="utf-8", newline="\n")
    script = to_wsl_path(str(win_tmp))
    wsl = wsl_exe() or "wsl.exe"
    wt = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe")
    if os.path.isfile(wt):
        subprocess.Popen(
            [wt, "new-tab", "--title", title, wsl, "-d", "Ubuntu", "-e", "bash", script],
            close_fds=True,
        )
    else:
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Start-Process -FilePath '{wsl}' -ArgumentList '-d','Ubuntu','-e','bash','{script}'",
            ],
            close_fds=True,
        )
    print(f"  cli {title}: launched")


def main() -> int:
    sync_browser_credentials_to_env(DATA)
    tok = openclaw_gateway_token()
    print(f"openclaw token: {tok[:8]}...")

    browsers = [
        ("lingzhao", "http://127.0.0.1:9120/?profile=lingzhao"),
        ("lingjin", "http://127.0.0.1:9121/?profile=lingjin"),
        ("lingtuo", "http://127.0.0.1:9122/?profile=lingtuo"),
        ("lingxi", "http://127.0.0.1:9123/?profile=lingxi"),
        ("lingxun", "http://127.0.0.1:9125/?profile=lingxun"),
        ("lingzhang", "http://127.0.0.1:9126/?profile=lingzhang"),
        ("xiaoqi", f"http://127.0.0.1:18789/chat?token={tok}"),
        ("yige", f"http://127.0.0.1:18790/chat?token={tok}"),
    ]
    print("=== browsers ===")
    for name, url in browsers:
        print(f"  {name}: {url}")
        _start_browser(url)
        time.sleep(0.2)

    print("=== clis ===")
    open_cli(
        "lingzhao",
        "docker exec -it docker-agents-hermes-1 hermes chat --profile lingzhao --yolo",
    )
    time.sleep(0.3)
    open_cli(
        "lingjin",
        "docker exec -it docker-agents-hermes-1 hermes chat --profile lingjin --yolo",
    )
    time.sleep(0.3)
    open_cli(
        "xiaoqi",
        "docker exec -it -e OPENCLAW_STATE_DIR=/workspace/data/.openclaw-xiaoqi "
        "docker-agents-openclaw-1 openclaw tui --local --session xiaoqi",
    )
    time.sleep(0.3)
    open_cli(
        "yige",
        "docker exec -it -e OPENCLAW_STATE_DIR=/workspace/data/.openclaw-yige "
        "docker-agents-openclaw-1 openclaw tui --local --session yige",
    )
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
