"""宿主 scan 单次执行器（Windows 计划任务 mailbus-host-scan 每 5 分钟调起）。

为什么存在：mailbus 容器里的 scan 无法推送 claude_code 消息（claude 桥
host-only，容器内无 PowerShell 直接跳过）——容器 agent 靠容器 scan（180s），
claude 系 agent（lingyan/lingyun）只能靠宿主 scan。宿主驱动过去是临时
while 循环，重启即失（2026-09 P11、2026-10 产线 s6 两次咬人），本任务兜底。

幂等性：scan 推送即标 inbox 消息 state=pushed（M2b 首派幂等），与容器
scan 并发安全，at-least-once 语义不变。
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "store", "logs", "host-scan.log")
MAX_LOG = 1_000_000


def main():
    os.chdir(ROOT)
    env = dict(os.environ, PYTHONUTF8="1")
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "bus.cli", "scan"],
            capture_output=True, text=True, timeout=280, env=env,
            encoding="utf-8", errors="replace",
        )
        rc = r.returncode
        tail = (r.stdout or "").strip().splitlines()
        summary = tail[-1] if tail else ""
    except subprocess.TimeoutExpired:
        rc, summary = "timeout", ""
    except Exception as e:
        rc, summary = "error", str(e)[:120]
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} rc={rc} {round(time.time()-t0, 1)}s {summary}\n"
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
            os.replace(LOG, LOG + ".old")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


if __name__ == "__main__":
    main()
