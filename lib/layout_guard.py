"""mail/ 与 mailbus-core/ 布局探测 — 防止 junction 下误删唯一源码树。"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LayoutReport:
    mail_path: Path
    core_path: Path
    mail_exists: bool
    core_exists: bool
    same_resolved_path: bool
    core_is_reparse: bool
    dedup_unsafe: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "mail_path": str(self.mail_path),
            "core_path": str(self.core_path),
            "mail_exists": self.mail_exists,
            "core_exists": self.core_exists,
            "same_resolved_path": self.same_resolved_path,
            "core_is_reparse": self.core_is_reparse,
            "dedup_unsafe": self.dedup_unsafe,
            "message": self.message,
        }


def _is_reparse_point(path: Path) -> bool:
    if not path.exists():
        return False
    if os.name == "nt":
        try:
            attrs = path.lstat().st_file_attributes  # type: ignore[attr-defined]
            return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (AttributeError, OSError):
            pass
    return path.is_symlink()


def layout_report(repo_parent: Path | None = None) -> LayoutReport:
    """探测 ai_tools 下 mail/ 与 mailbus-core/ 是否为同一物理树。"""
    base = Path(repo_parent or Path(__file__).resolve().parents[2]).resolve()
    mail = base / "mail"
    core = base / "mailbus-core"
    mail_exists = mail.exists()
    core_exists = core.exists()

    same = False
    if mail_exists and core_exists:
        try:
            same = os.path.samefile(mail, core)
        except OSError:
            same = mail.resolve() == core.resolve()

    core_reparse = _is_reparse_point(core) if core_exists else False
    dedup_unsafe = same

    if dedup_unsafe:
        msg = (
            "mail/ 与 mailbus-core/ 解析为同一路径（多为 junction）。"
            "禁止对 mail/ 做「删代码留 store」去重 — 会删除唯一源码。"
        )
    elif core_reparse and mail_exists:
        msg = "mailbus-core 为 reparse 点；去重前须确认未指向 mail/。"
    else:
        msg = "mail/ 与 mailbus-core/ 为独立目录，可按计划拆分源码与数据。"

    return LayoutReport(
        mail_path=mail,
        core_path=core,
        mail_exists=mail_exists,
        core_exists=core_exists,
        same_resolved_path=same,
        core_is_reparse=core_reparse,
        dedup_unsafe=dedup_unsafe,
        message=msg,
    )


def assert_safe_for_mail_code_dedup(repo_parent: Path | None = None) -> None:
    """去重/删 mail 代码树前调用；不安全则 SystemExit(2)。"""
    report = layout_report(repo_parent)
    if report.dedup_unsafe:
        raise SystemExit(
            f"ERROR: layout hazard — {report.message}\n"
            f"  mail={report.mail_path}\n"
            f"  mailbus-core={report.core_path}\n"
            "  解除 junction 或改为物理拆分后再去重。"
        )
