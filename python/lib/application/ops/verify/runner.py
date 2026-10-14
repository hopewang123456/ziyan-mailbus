"""统一 verify 入口 — 字段校验 + git + pytest。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from .git_check import git_diff_stat
from .pytest_runner import run_pytest
from .step_verify import verify_step_result


def _verify_cfg(config: dict) -> dict:
    auto = config.get("mailbus_automation") or {}
    return auto.get("verify") or {}


def run_step_verify(
    role_type: Optional[int],
    conclusion: str,
    result: dict,
    *,
    config: dict,
    data_dir: str = "",
) -> Tuple[bool, Optional[str], dict]:
    """返回 (ok, error, meta)。"""
    vc = _verify_cfg(config)
    strict = bool(vc.get("strict"))
    meta: Dict[str, Any] = {"strict": strict}

    ok, err = verify_step_result(role_type, conclusion, result, strict=strict)
    if not ok:
        return False, err, meta

    repo = vc.get("repo_root") or ""
    if not repo and data_dir:
        repo = os.path.dirname(os.path.normpath(data_dir))

    c = (conclusion or "").lower()
    details = result.get("details") or result
    if not isinstance(details, dict):
        details = {}

    if role_type == 8 and c in ("done", "pass") and vc.get("git_diff_on_dev_done", True):
        if not details.get("git_diff_stat") and not details.get("files_changed"):
            has, gerr, stat = git_diff_stat(repo)
            meta["git_diff_stat"] = stat[:200]
            if not has and strict:
                return False, gerr or "no git diff", meta

    if role_type == 6 and c == "pass" and vc.get("pytest_on_test_pass", False):
        if not details.get("pytest_ran"):
            targets = vc.get("pytest_targets") or ["tests"]
            passed, summary = run_pytest(repo, targets, timeout=int(vc.get("pytest_timeout") or 300))
            meta["pytest_summary"] = summary
            if not passed:
                return False, f"pytest failed: {summary}", meta

    if role_type == 6 and c == "pass" and strict:
        from .deliverable_check import verify_deliverable_playability

        d_ok, d_err, d_meta = verify_deliverable_playability(
            details, data_dir=data_dir, strict=strict, vc=vc,
        )
        meta.update(d_meta)
        if not d_ok:
            return False, d_err or "deliverable verify failed", meta

    if role_type == 10 and c in ("done", "pass", "dispatched") and strict:
        from .deliverable_check import check_windows_launch_files, _deliverable_dir

        ddir = _deliverable_dir(details, data_dir)
        required = vc.get("acceptance_deliverable_files") or [
            "play.ps1", "play.bat", "play-auto.bat",
        ]
        if ddir:
            missing = [f for f in required if not os.path.isfile(os.path.join(ddir, f))]
            if missing and vc.get("require_launch_matrix", False):
                return False, f"missing launch files: {missing}", meta
            ok, msg = check_windows_launch_files(ddir)
            meta["windows_launch"] = msg
            if not ok and vc.get("require_launch_matrix", False):
                return False, msg, meta

    if role_type == 5 and c == "pass":
        from .harness_report import verify_harness_report

        h_ok, h_err, h_meta = verify_harness_report(result, data_dir, strict=strict)
        meta.update(h_meta)
        if not h_ok:
            return False, h_err, meta

    return True, None, meta
