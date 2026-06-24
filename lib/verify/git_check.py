"""Git diff 证据检查 — 开发步骤验证。"""

from __future__ import annotations

import os
import subprocess
from typing import Optional, Tuple


def git_diff_stat(repo_root: str, *, base_ref: str = "HEAD") -> Tuple[bool, Optional[str], str]:
    """返回 (has_changes, error, stat_text)。"""
    if not repo_root or not os.path.isdir(repo_root):
        return True, None, ""
    git_dir = os.path.join(repo_root, ".git")
    if not os.path.isdir(git_dir):
        return True, None, ""
    try:
        r = subprocess.run(
            ["git", "diff", "--stat", base_ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return True, None, r.stderr.strip()[:200]
        stat = (r.stdout or "").strip()
        if not stat:
            return False, "未检测到 git diff 变更", stat
        return True, None, stat
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return True, None, str(exc)
