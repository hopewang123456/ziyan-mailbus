"""Quality Harness 审阅步轻量校验 — 报告存在性与 commit_sha 一致。"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from ..utils import json_read


def _details_and_extensions(result: dict) -> tuple[dict, dict]:
    details = result.get("details") or result
    if not isinstance(details, dict):
        details = {}
    ext = details.get("extensions") or result.get("extensions") or {}
    if not isinstance(ext, dict):
        ext = {}
    return details, ext


def _resolve_report_path(data_dir: str, result: dict) -> tuple[Optional[str], str]:
    """从 attachments 或 commit_sha 推断报告路径。"""
    details, ext = _details_and_extensions(result)
    sha = str(ext.get("commit_sha") or details.get("commit_sha") or "").strip()

    for att in result.get("attachments") or details.get("attachments") or []:
        if not isinstance(att, dict) or att.get("kind") != "report":
            continue
        ref = str(att.get("ref") or "").replace("\\", "/").strip()
        if not ref:
            continue
        if ref.startswith("store/"):
            ref = ref[len("store/") :]
        return os.path.join(data_dir, ref), sha

    if sha:
        return os.path.join(data_dir, "reports", f"{sha}.json"), sha
    return None, sha


def verify_harness_report(
    result: dict,
    data_dir: str,
    *,
    strict: bool = False,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """当 step-result 含 harness_verdict 时校验关联报告。"""
    details, ext = _details_and_extensions(result)
    verdict = ext.get("harness_verdict") or details.get("harness_verdict")
    if not verdict:
        return True, None, {}

    path, sha = _resolve_report_path(data_dir, result)
    meta: Dict[str, Any] = {
        "harness_verdict": str(verdict).upper(),
        "commit_sha": sha,
    }

    if not sha and strict:
        return False, "harness review missing commit_sha", meta

    if not path or not os.path.isfile(path):
        if strict or str(verdict).upper() == "APPROVE":
            return False, "harness report file missing", meta
        return True, None, meta

    report = json_read(path, {})
    if report.get("schema") != "code-review-report-v1":
        return False, "harness report schema mismatch", meta

    report_sha = str(report.get("commit_sha") or "")
    if sha and report_sha and sha != report_sha:
        return False, f"commit_sha mismatch: expected {sha[:12]} got {report_sha[:12]}", meta

    meta["report_aggregate_status"] = report.get("aggregate_status")
    meta["report_path"] = path
    return True, None, meta
