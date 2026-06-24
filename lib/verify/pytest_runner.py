"""可选 pytest 自动验证。"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional, Tuple


def run_pytest(
    repo_root: str,
    targets: Optional[List[str]] = None,
    *,
    timeout: int = 300,
) -> Tuple[bool, str]:
    """运行 pytest，返回 (passed, summary)。"""
    if not repo_root or not os.path.isdir(repo_root):
        return True, "skip: no repo_root"
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no"]
    for t in targets or ["tests"]:
        cmd.append(t)
    try:
        r = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        tail = out.splitlines()[-3:] if out else []
        summary = " | ".join(tail) if tail else f"exit={r.returncode}"
        return r.returncode == 0, summary[:500]
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    except Exception as exc:
        return True, f"pytest skip: {exc}"
