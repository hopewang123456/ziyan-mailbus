"""Quality Harness code-review-report-v1 只读 API 辅助。"""
from __future__ import annotations

import os
import re

from lib.infra.utils import json_read

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def normalize_commit_sha(raw: str) -> str | None:
    """接受 7–40 位 hex 或 ``{sha}.json`` 文件名。"""
    s = (raw or "").strip().strip("/")
    if s.endswith(".json"):
        s = s[:-5]
    if not _SHA_RE.fullmatch(s):
        return None
    return s.lower()


def harness_report_path(data_dir: str, sha: str) -> str | None:
    """``store/reports/{sha}.json`` 安全路径；不存在则 None。"""
    norm = normalize_commit_sha(sha)
    if not norm:
        return None
    root = os.path.realpath(data_dir)
    fname = f"{norm}.json"
    fpath = os.path.realpath(os.path.join(data_dir, "reports", fname))
    if not fpath.startswith(root + os.sep):
        return None
    return fpath if os.path.isfile(fpath) else None


def resolve_ref_path(data_dir: str, ref: str) -> str | None:
    """``store/reports/...`` 或 ``reports/...`` 相对 ref → 绝对路径。"""
    r = (ref or "").replace("\\", "/").strip()
    if not r:
        return None
    if r.startswith("store/"):
        r = r[len("store/") :]
    name = os.path.basename(r)
    if not name or name != os.path.basename(r) or ".." in name:
        return None
    root = os.path.realpath(data_dir)
    fpath = os.path.realpath(os.path.join(data_dir, "reports", name))
    if not fpath.startswith(root + os.sep):
        return None
    return fpath if os.path.isfile(fpath) else None


def load_harness_report(data_dir: str, sha: str) -> dict | None:
    path = harness_report_path(data_dir, sha)
    if not path:
        return None
    doc = json_read(path, {})
    return doc if isinstance(doc, dict) and doc.get("schema") == "code-review-report-v1" else None


def harness_report_summary(report: dict) -> dict:
    """Dashboard / API 用精简摘要。"""
    layers = report.get("layers") or {}
    layer_status = {
        k: (v or {}).get("status")
        for k, v in layers.items()
        if isinstance(v, dict) and v.get("status")
    }
    ai = layers.get("ai_review") if isinstance(layers.get("ai_review"), dict) else {}
    return {
        "schema": report.get("schema"),
        "commit_sha": report.get("commit_sha"),
        "aggregate_status": report.get("aggregate_status"),
        "trigger": report.get("trigger"),
        "timestamp": report.get("timestamp"),
        "author_agent": report.get("author_agent"),
        "blocking": report.get("blocking"),
        "layers": layer_status,
        "ai_review_summary": (ai.get("summary") or "")[:500] or None,
        "repo": (report.get("repo") or {}).get("name"),
    }
