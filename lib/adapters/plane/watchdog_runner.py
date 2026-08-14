"""launch watchdog — 纯 Python 版（原 mailbus-launch-watchdog.sh）。

监听 ``run/launch-queue`` 目录下 ``*.launch`` 文件（格式：第1行 cmd、第2行 title、
第3行可选 mode=background/interactive），在宿主侧启动 Agent 窗口。

- Windows 宿主：经 PowerShell ``Start-Process`` 启动 WSL 窗口（background 隐藏 / interactive 可见）
- Linux/WSL 宿主：直接 ``bash -c`` 后台执行
"""
from __future__ import annotations

import contextlib
import glob
import os
import subprocess
import sys
import time
from typing import Optional

from lib.infra.env_bootstrap import mailbus_paths

PS_EXE = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS_CMD = "/mnt/c/Windows/System32/cmd.exe"
WSL_WIN = r"C:\Windows\System32\wsl.exe"


def _log(msg: str) -> None:
    print(f"[mailbus-watchdog] {msg}", flush=True)


def _launch_mode_for(cmd: str, mode: str) -> str:
    mode = (mode or "background").strip()
    if mode == "interactive":
        return "interactive"
    if any(k in cmd for k in ("docker exec -it", "openclaw tui", "-NoExit", "powershell.*NoExit")):
        return "interactive"
    return "background"


def _windows_launch_visible(script: str, title: str) -> bool:
    if os.path.isfile(PS_EXE):
        r = subprocess.run(
            [
                PS_EXE,
                "-NoProfile",
                "-Command",
                f"Start-Process -FilePath '{WSL_WIN}' -ArgumentList '-d','Ubuntu','-e','bash','{script}'",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0
    if os.path.isfile(WINDOWS_CMD):
        r = subprocess.run(
            [WINDOWS_CMD, "/c", "start", "", WSL_WIN, "-d", "Ubuntu", "-e", "bash", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0
    _log("ERROR: 找不到 PowerShell 或 cmd.exe")
    return False


def _windows_launch_hidden(script: str, title: str) -> bool:
    if os.path.isfile(PS_EXE):
        r = subprocess.run(
            [
                PS_EXE,
                "-NoProfile",
                "-Command",
                f"Start-Process -WindowStyle Hidden -FilePath '{WSL_WIN}' "
                f"-ArgumentList '-d','Ubuntu','-e','bash','{script}'",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0
    if os.path.isfile(WINDOWS_CMD):
        r = subprocess.run(
            [WINDOWS_CMD, "/c", "start", "/min", "", WSL_WIN, "-d", "Ubuntu", "-e", "bash", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0
    _log("ERROR: 找不到 PowerShell 或 cmd.exe")
    return False


def _launch_one(path: str, workdir: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        _log(f"read failed {path}: {exc}")
        return
    cmd = (lines[0] if lines else "").strip()
    title = (lines[1] if len(lines) > 1 else "").strip() or "Agent"
    mode = (lines[2] if len(lines) > 2 else "").strip()
    if not cmd:
        with contextlib.suppress(OSError):
            os.remove(path)
        return

    ts = int(time.time())
    launch_mode = _launch_mode_for(cmd, mode)

    if launch_mode == "interactive":
        vis_script = f"/tmp/launch-interactive-{ts}.sh"
        body = (
            "#!/bin/bash\nset +e\n"
            f"cd {workdir}\n{cmd}\n"
            "EXIT_CODE=$?\necho \"\"\n"
            'if [ $EXIT_CODE -ne 0 ]; then\n  echo "⚠️  脚本异常退出 (code: $EXIT_CODE)"\n'
            'else\n  echo "✅ 脚本执行完毕 (code: $EXIT_CODE)"\nfi\n'
            f'echo "--- {title} 执行完毕 $(date) ---" >> /tmp/mailbus-launch.log 2>&1\n'
            'echo "按 Enter 键关闭窗口..."\nread\n'
        )
        with open(vis_script, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(vis_script, 0o755)
        ok = _windows_launch_visible(vis_script, title)
        _log(f"v15 已启动(interactive): {title}" if ok else f"FAILED interactive: {title}")
        with contextlib.suppress(OSError):
            os.remove(path)
        return

    wrapper = f"/tmp/launch-ps-wrapper-{ts}.sh"
    body = (
        "#!/bin/bash\n"
        f"cd {workdir}\n{cmd}\n"
        f'echo "--- {title} 执行完毕 $(date) ---" >> /tmp/mailbus-launch.log 2>&1\n'
    )
    with open(wrapper, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(wrapper, 0o755)

    if sys.platform == "win32":
        ok = _windows_launch_hidden(wrapper, title)
    else:
        try:
            proc = subprocess.Popen(["bash", "-c", f"cd {workdir} && bash {wrapper} &"], start_new_session=True)
            ok = proc.poll() is None
        except OSError:
            ok = False
    _log(f"v15 已启动(background): {title}" if ok else f"FAILED background: {title}")
    with contextlib.suppress(OSError):
        os.remove(path)


def run_watchdog_forever(queue_dir: Optional[str] = None) -> int:
    """前台循环监听 launch-queue（供 mailbus.py watchdog run / systemd 使用）。"""
    paths = mailbus_paths()
    qdir = queue_dir or os.path.join(paths["run_dir"], "launch-queue")
    os.makedirs(qdir, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(qdir, 0o777)
    _log(f"v15 启动，监听 {qdir} ...")

    root = paths["root"]
    workdir = os.environ.get("MAILBUS_LAUNCH_WORKDIR", "/mnt/e")
    if not os.path.isdir(workdir):
        workdir = str(root)

    while True:
        try:
            for file in sorted(glob.glob(os.path.join(qdir, "*.launch"))):
                processing = f"{file}.{os.getpid()}.processing"
                try:
                    if not os.path.exists(file):
                        continue
                    # 原子抢占：只有一个 watchdog 能 mv 成功，避免双实例各弹一窗
                    os.rename(file, processing)
                except OSError:
                    continue
                _launch_one(processing, workdir)
        except Exception as exc:  # noqa: BLE001 — 守护进程须保活
            _log(f"loop error: {exc}")
        time.sleep(1)


def main() -> int:
    queue_dir = os.environ.get("MAILBUS_LAUNCH_QUEUE", "").strip() or None
    return run_watchdog_forever(queue_dir)


if __name__ == "__main__":
    raise SystemExit(main())
