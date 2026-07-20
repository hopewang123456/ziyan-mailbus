"""Git diff 证据采集（verify 可选）。"""
from __future__ import annotations

import subprocess
from typing import Optional, Tuple


def git_diff_stat(repo_root: str) -> Tuple[bool, Optional[str], str]:
    """返回 (has_changes, error, stat_text)。"""
    if not repo_root:
        return False, "missing repo_root", ""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "diff", "--stat"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc), ""
    stat = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git diff failed").strip()
        return False, err[:200], stat
    if not stat:
        return False, "no git diff", ""
    return True, None, stat
