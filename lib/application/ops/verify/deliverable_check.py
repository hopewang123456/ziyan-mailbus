"""交付物玩法 / 交互 / Windows 启动门禁。"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple


def _deliverable_dir(details: dict, data_dir: str) -> Optional[str]:
    d = details.get("deliverable_dir") or details.get("deliverable") or ""
    if not d:
        return None
    if os.path.isabs(d):
        return d if os.path.isdir(d) else None
    base = data_dir or ""
    path = os.path.join(base, d) if base else d
    return path if os.path.isdir(path) else None


def run_scripted_interactive(
    deliverable_dir: str,
    *,
    stdin_text: str = "A\nB\nC\n",
    timeout: int = 60,
) -> Tuple[bool, str]:
    """scripted stdin 三轮选路线。"""
    main_py = os.path.join(deliverable_dir, "game", "main.py")
    if not os.path.isfile(main_py):
        alt = os.path.join(deliverable_dir, "main.py")
        if os.path.isfile(alt):
            main_py = alt
        else:
            return False, "main.py not found"
    cwd = deliverable_dir
    cmd = [sys.executable, "-m", "game.main", "--plain"]
    if not os.path.isdir(os.path.join(deliverable_dir, "game")):
        cmd = [sys.executable, main_py, "--plain"]
    try:
        r = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, "interactive E2E timeout"
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return False, f"interactive exit {r.returncode}: {out[:200]}"
    if "选择路线" not in out:
        return False, "stdout missing 选择路线"
    if out.find("选择路线") > out.rfind("今日信件") and "今日信件" in out:
        pass  # order ok when both present
    elif "今日信件" in out and out.index("今日信件") > out.index("选择路线"):
        return False, "interactive flow: 选择路线 before 今日信件"
    return True, "interactive ok"


def check_windows_launch_files(deliverable_dir: str) -> Tuple[bool, str]:
    """Windows 启动矩阵：play.ps1 / play.bat / play-auto.bat 存在且 bat 默认非 --auto。"""
    issues = []
    ps1 = os.path.join(deliverable_dir, "play.ps1")
    bat = os.path.join(deliverable_dir, "play.bat")
    auto_bat = os.path.join(deliverable_dir, "play-auto.bat")
    if not os.path.isfile(ps1):
        issues.append("missing play.ps1")
    if not os.path.isfile(bat):
        issues.append("missing play.bat")
    if os.path.isfile(bat):
        try:
            text = open(bat, encoding="utf-8", errors="replace").read()
            if "--auto" in text and "play-auto" not in os.path.basename(bat):
                first_lines = "\n".join(text.splitlines()[:5])
                if "--auto" in first_lines and "play-auto" not in first_lines:
                    issues.append("play.bat defaults to --auto")
        except OSError as exc:
            issues.append(f"play.bat read: {exc}")
    if sys.platform == "win32" and os.path.isfile(ps1):
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"& {{ $null = [System.Management.Automation.Language.Parser]::ParseFile('{ps1.replace(chr(39), chr(39)+chr(39))}', [ref]$null, [ref]$errs); if ($errs) {{ exit 1 }} }}"],
                capture_output=True,
                timeout=30,
                text=True,
            )
            if r.returncode != 0:
                issues.append("play.ps1 ParserError")
        except (subprocess.TimeoutExpired, OSError):
            issues.append("play.ps1 syntax check failed")
    if issues:
        return False, "; ".join(issues)
    return True, "windows launch ok"


def verify_acceptance_criteria(
    criteria: list,
    details: dict,
    *,
    data_dir: str = "",
    strict: bool = False,
) -> Tuple[bool, Optional[str]]:
    """对照 task.extensions.acceptance_criteria 链式验收项。"""
    if not criteria or not strict:
        return True, None
    missing = [c for c in criteria if isinstance(c, str) and c not in str(details)]
    if missing and strict:
        return False, f"missing criteria evidence: {missing[:3]}"
    return True, None


def verify_deliverable_playability(
    details: dict,
    *,
    data_dir: str = "",
    strict: bool = False,
    vc: Optional[dict] = None,
) -> Tuple[bool, Optional[str], dict]:
    """role_type=6 扩展：pytest 之外跑交互 + Win 启动（若 deliverable_dir 存在）。"""
    meta: Dict[str, Any] = {}
    if not strict:
        return True, None, meta
    vc = vc or {}
    ddir = _deliverable_dir(details, data_dir)
    if not ddir:
        if vc.get("require_deliverable_dir"):
            return False, "missing deliverable_dir", meta
        return True, None, meta

    if vc.get("scripted_interactive_on_test_pass", True):
        ok, msg = run_scripted_interactive(ddir)
        meta["scripted_interactive"] = msg
        if not ok:
            return False, msg, meta

    if vc.get("windows_launch_check", True):
        ok, msg = check_windows_launch_files(ddir)
        meta["windows_launch"] = msg
        if not ok and sys.platform == "win32":
            return False, msg, meta
        if not ok and vc.get("windows_launch_required"):
            return False, msg, meta

    criteria = details.get("acceptance_criteria") or details.get("acceptance_checklist") or []
    if isinstance(criteria, list):
        ok, err = verify_acceptance_criteria(criteria, details, data_dir=data_dir, strict=strict)
        if not ok:
            return False, err, meta

    for field in ("interactive_ran", "auto_ran", "windows_launch_ok"):
        if vc.get("require_test_paths") and not details.get(field):
            return False, f"missing details.{field}", meta

    return True, None, meta
