"""G6 仓库卫生守卫：根目录白名单 + 禁止备份/运行数据入库。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import REPO_ROOT  # noqa: E402

# run/ 与 store/ 是 docker-compose 约定的宿主运行目录（MAILBUS_HOST_ROOT），
# 可能由联调脚本或容器挂载生成，允许存在但不允许有内容入库。
ALLOWED_DIRS = {
    "config",
    "data",
    "docs",
    "java",
    "python",
    "run",
    "shared",
    "store",
    "web",
}
ALLOWED_FILES = {
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "README.zh.md",
}
_IGNORED_PARTS = {".git", "node_modules", "target", "data", "__pycache__", ".pytest_cache"}


def test_root_entries_are_whitelisted() -> None:
    unexpected = []
    for entry in REPO_ROOT.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and entry.name not in ALLOWED_DIRS:
            unexpected.append(f"{entry.name}/")
        elif entry.is_file() and entry.name not in ALLOWED_FILES:
            unexpected.append(entry.name)
    assert not unexpected, "根目录出现白名单外条目：" + ", ".join(sorted(unexpected))


def test_no_backup_files_in_repo() -> None:
    offenders = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _IGNORED_PARTS & set(path.parts):
            continue
        if ".bak" in path.name or path.suffix in {".log", ".db"}:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, "仓库内出现备份/运行数据：" + ", ".join(offenders[:10])
