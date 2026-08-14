"""Pytest 子进程执行（verify 可选）。"""
from __future__ import annotations

import subprocess
from typing import List, Tuple


def run_pytest(repo_root: str, targets: List[str], *, timeout: int = 300) -> Tuple[bool, str]:
    """返回 (passed, summary)。"""
    if not repo_root:
        return False, "missing repo_root"
    cmd = ["python", "-m", "pytest", *targets, "-q"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    summary = (proc.stdout or proc.stderr or "").strip()[-500:]
    return proc.returncode == 0, summary or f"exit {proc.returncode}"
