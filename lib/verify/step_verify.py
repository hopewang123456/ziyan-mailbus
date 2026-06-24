"""步骤产出验证 — 降低 agent 空报完成。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def verify_step_result(
    role_type: Optional[int],
    conclusion: str,
    result: dict,
    *,
    strict: bool = False,
) -> Tuple[bool, Optional[str]]:
    """按 role_type 校验 step result。strict=False 时仅做轻量字段检查。"""
    c = (conclusion or "").lower()
    details = result.get("details") or result
    if isinstance(details, dict) and details is not result:
        merged = dict(details)
        merged.setdefault("summary", result.get("summary"))
        details = merged
    elif not isinstance(details, dict):
        details = result

    if role_type == 8 and c in ("done", "pass"):
        return verify_dev_done(details, strict=strict)
    if role_type == 6 and c == "pass":
        return verify_test_done(details, strict=strict)
    if role_type == 5 and c == "pass":
        return verify_review_done(details, strict=strict)
    if role_type == 9 and c == "dispatched":
        nxt = details.get("next_assignee") or details.get("dispatched_to")
        if not nxt and strict:
            return False, "missing dispatch target"
    return True, None


def verify_dev_done(report: dict, *, strict: bool = False) -> Tuple[bool, Optional[str]]:
    details = report if isinstance(report, dict) else {}
    if details.get("self_test") == "fail":
        return False, "self_test failed"
    if strict:
        if not (details.get("files_changed") or details.get("git_diff_stat") or details.get("deliverable")):
            return False, "no deliverable or diff evidence"
    if details.get("self_test") not in (None, "pass", "skip") and not details.get("deliverable"):
        return False, "missing deliverable"
    return True, None


def verify_test_done(report: dict, *, strict: bool = False) -> Tuple[bool, Optional[str]]:
    details = report if isinstance(report, dict) else {}
    results = details.get("results")
    if not results and strict:
        return False, "missing test results"
    if isinstance(results, list):
        failed = [r for r in results if str(r.get("status", "")).lower() in ("fail", "failed", "error")]
        if failed:
            return False, f"{len(failed)} test case(s) failed in report"
        if strict and not results:
            return False, "empty results list"
    passed = details.get("passed")
    failed_n = details.get("failed")
    if passed is not None and failed_n is not None:
        try:
            if int(failed_n) > 0:
                return False, "failed count > 0"
        except (TypeError, ValueError):
            pass
    return True, None


def verify_review_done(report: dict, *, strict: bool = False) -> Tuple[bool, Optional[str]]:
    details = report if isinstance(report, dict) else {}
    if strict and not details.get("review_tool"):
        return False, "missing review_tool"
    if strict and not details.get("passed_checks") and not details.get("issues"):
        return False, "missing review evidence"
    return True, None
