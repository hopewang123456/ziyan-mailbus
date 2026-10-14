"""API 安全辅助：路径/agent 名校验。"""

import os
import re

_AGENT_RE = re.compile(r"^[a-z0-9_-]+$")


def validate_agent_name(agent: str, agents: dict) -> bool:
    if not agent or not _AGENT_RE.match(agent):
        return False
    return agent in agents


def safe_report_path(data_dir: str, subdir: str, filename: str) -> str | None:
    """返回 data_dir 下安全可读的文件路径，否则 None。"""
    name = os.path.basename(filename or "")
    if not name or name != filename or ".." in name:
        return None
    root = os.path.realpath(data_dir)
    fpath = os.path.realpath(os.path.join(data_dir, subdir, name))
    if not fpath.startswith(root + os.sep):
        return None
    return fpath if os.path.isfile(fpath) else None
