#!/usr/bin/env python3
"""阶段 0–4 统一验收：单元测试 + drill + smoke + API health。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.constants import DEFAULT_API_BASE
from lib.utils import configure_stdio_utf8

configure_stdio_utf8()


class Step:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail = ""
        self.optional = False


def _summarize_json_output(out: str, *, keys: tuple[str, ...] = ("ok",)) -> str:
    """从工具 stdout 提取 JSON 摘要，避免验收报告只显示 '}'。"""
    if not out:
        return ""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("summary:"):
                return line
            if line and line not in ("}", "{"):
                return line[:200]
        return out.splitlines()[-1][:200] if out.splitlines() else ""
    parts = []
    for key in keys:
        val = data.get(key)
        if isinstance(val, dict):
            parts.append(f"{key}={val}")
        else:
            parts.append(f"{key}={val}")
    return " ".join(parts)


def _run_py(script: str, *args: str, timeout: int = 600) -> tuple[int, str]:
    cmd = [sys.executable, os.path.join(ROOT, script), *args]
    r = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONPATH": ROOT, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()


def _api_health(base: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/status", timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sched = (data.get("scheduler") or {}).get("running")
        return True, f"scheduler.running={sched}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)


def main() -> int:
    ap_base = os.environ.get("MAILBUS_URL") or os.environ.get("MAILBUS_API") or DEFAULT_API_BASE
    data_dir = os.path.join(ROOT, "store")
    results: list[Step] = []

    # 1. 单元测试
    s = Step("tests/run_all.py")
    rc, out = _run_py("tests/run_all.py", timeout=900)
    s.ok = rc == 0
    s.detail = out.splitlines()[-1] if out else f"exit {rc}"
    results.append(s)

    # 2. video_publish drill (dry)
    s = Step("test-video-publish-drill (dry)")
    rc, out = _run_py("tools/tools/ops/test-video-publish-drill.py", "--data-dir", data_dir)
    s.ok = rc == 0
    s.detail = out.splitlines()[-1] if out else f"exit {rc}"
    results.append(s)

    # 3. platform-scout smoke (offline)
    s = Step("smoke-platform-scout (offline)")
    rc, out = _run_py("tools/tools/ops/smoke-platform-scout.py", "--data-dir", data_dir)
    s.ok = rc == 0
    s.detail = "\n".join(out.splitlines()[:4])
    results.append(s)

    # 3b. order-intake schema
    s = Step("validate-order-intake")
    rc, out = _run_py("tools/validate-order-intake.py", "--data-dir", data_dir)
    s.ok = rc == 0
    s.detail = out.splitlines()[-1] if out else f"exit {rc}"
    results.append(s)

    # 4. inbox archive dry-run
    s = Step("archive-inbox-backlog (dry-run)")
    rc, out = _run_py(
        "tools/tools/ops/archive-inbox-backlog.py",
        "--data-dir", data_dir,
        "--before", "2026-06-15",
    )
    s.ok = rc == 0
    s.detail = out.splitlines()[-1] if out else f"exit {rc}"
    results.append(s)

    # 5. API health（可选 — mailbus 未启动时不失败整包）
    s = Step("api/status health")
    s.optional = True
    ok, detail = _api_health(ap_base)
    s.ok = ok
    s.detail = f"{ap_base} — {detail}"
    results.append(s)

    # 6. validate-scheduler（仅 API 在线时）
    if ok:
        s = Step("validate-scheduler")
        s.optional = True
        rc, out = _run_py("tools/validate-scheduler.py", "--url", ap_base)
        s.ok = rc == 0
        s.detail = _summarize_json_output(out, keys=("ok", "scheduler"))
        results.append(s)

    # 7. Dashboard API smoke（可选）
    if ok:
        s = Step("smoke-dashboard-api")
        s.optional = True
        rc, out = _run_py("tools/tools/ops/smoke-dashboard-api.py")
        s.ok = rc == 0
        s.detail = out.splitlines()[-1] if out else f"exit {rc}"
        results.append(s)

    print("=" * 60)
    print("  mailbus 统一验收报告")
    print("=" * 60)
    failed = 0
    for st in results:
        if st.ok:
            mark = "PASS"
        elif st.optional:
            mark = "SKIP"
        else:
            mark = "FAIL"
            failed += 1
        opt = " (optional)" if st.optional else ""
        print(f"\n[{mark}]{opt} {st.name}")
        for line in (st.detail or "").splitlines():
            safe = line.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"       {safe}")

    print("\n" + "=" * 60)
    required_fail = sum(1 for st in results if not st.ok and not st.optional)
    if required_fail:
        print(f"验收未通过：{required_fail} 项必需检查失败")
        return 1
    print("验收通过（必需项全部 OK；可选项见 SKIP）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
