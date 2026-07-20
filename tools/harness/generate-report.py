#!/usr/bin/env python3
"""从 git + pytest 结果生成 code-review-report-v1（Quality Harness Layer 1/2）。

规范：mail/docs/quality-harness-pipeline-spec.md §3.2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

MAIL_ROOT = Path(__file__).resolve().parents[2]
_STATUS_RANK = {"skip": 0, "pass": 1, "warn": 2, "fail": 3, "error": 4}
_BASELINE_SCHEMA = "harness-pytest-baseline-v1"


def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _changed_py_files(repo: Path, commit: str = "HEAD") -> list[str]:
    diff_range = f"{commit}~1..{commit}" if commit != "WORKTREE" else None
    args = ["diff", "--name-only", diff_range] if diff_range else ["diff", "--name-only", "HEAD"]
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [f for f in proc.stdout.strip().splitlines() if f.endswith(".py")]


def _merge_status(*statuses: str) -> str:
    best = "skip"
    for st in statuses:
        if _STATUS_RANK.get(st, 0) > _STATUS_RANK.get(best, 0):
            best = st
    return best


def _baseline_path(repo: Path) -> Path:
    return repo / "store" / "reports" / "baseline.json"


def _load_baseline(repo: Path) -> set[str]:
    path = _baseline_path(repo)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(data.get("failed_nodeids") or [])


def _write_baseline(repo: Path, failed_nodeids: set[str] | list[str]) -> Path:
    path = _baseline_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": _BASELINE_SCHEMA,
        "failed_nodeids": sorted(failed_nodeids),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _parse_junit_failures(junit_path: Path) -> list[str]:
    if not junit_path.is_file():
        return []
    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError:
        return []
    nodeids: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        fpath = case.get("file") or ""
        name = case.get("name") or ""
        classname = case.get("classname") or ""
        if fpath:
            if classname and classname.split(".")[-1] not in (name, fpath.replace("/", ".").replace(".py", "")):
                cls = classname.split(".")[-1]
                if cls and cls != name and not cls.endswith("py"):
                    nodeids.append(f"{fpath}::{cls}::{name}")
                else:
                    nodeids.append(f"{fpath}::{name}")
            else:
                nodeids.append(f"{fpath}::{name}")
        elif classname:
            nodeids.append(f"{classname}::{name}")
        elif name:
            nodeids.append(name)
    return nodeids


def _apply_baseline_comparison(regression: dict, repo: Path) -> dict:
    pytest_info = regression.setdefault("pytest", {})
    current = set(pytest_info.get("failed_nodeids") or [])
    baseline = _load_baseline(repo)
    pytest_info["new_failures_vs_baseline"] = sorted(current - baseline)
    return regression


def _run_pytest(repo: Path) -> dict:
    if not (repo / "tests").is_dir():
        return {
            "status": "skip",
            "pytest": {"total": 0, "passed": 0, "failed": 0, "new_failures_vs_baseline": []},
        }
    junit_path = Path(tempfile.mkdtemp()) / "pytest-junit.xml"
    try:
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest", "tests", "-q", "--tb=no",
                    f"--junitxml={junit_path}",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "error", "pytest": {"error": str(exc), "new_failures_vs_baseline": []}}
        summary = (proc.stdout or proc.stderr or "").strip().splitlines()
        tail = summary[-1] if summary else ""
        failed_nodeids = _parse_junit_failures(junit_path)
        failed = len(failed_nodeids) if failed_nodeids else (1 if proc.returncode != 0 else 0)
        status = "pass" if proc.returncode == 0 else "fail"
        layer = {
            "status": status,
            "pytest": {
                "exit_code": proc.returncode,
                "summary_line": tail,
                "failed": failed,
                "failed_nodeids": failed_nodeids,
            },
        }
        return _apply_baseline_comparison(layer, repo)
    finally:
        shutil.rmtree(junit_path.parent, ignore_errors=True)


def _run_pylint(repo: Path, files: list[str]) -> dict:
    if not shutil.which("pylint"):
        return {"status": "skip", "reason": "pylint not found"}
    if not files:
        return {"status": "skip", "reason": "no python files changed"}
    targets = [str(repo / f) for f in files]
    try:
        proc = subprocess.run(
            ["pylint", "--output-format=text", "--score=y"] + targets,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}
    score = None
    for line in (proc.stdout or "").splitlines():
        m = re.search(r"rated at ([\d.]+)/10", line)
        if m:
            score = float(m.group(1))
            break
    st = "pass" if proc.returncode == 0 else "warn"
    out: dict = {"status": st, "exit_code": proc.returncode}
    if score is not None:
        out["score"] = score
    return out


def _run_mypy(repo: Path, files: list[str]) -> dict:
    if not shutil.which("mypy"):
        return {"status": "skip", "reason": "mypy not found"}
    if not files:
        return {"status": "skip", "reason": "no python files changed"}
    targets = [str(repo / f) for f in files]
    try:
        proc = subprocess.run(
            ["mypy", "--show-error-codes"] + targets,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}
    errors = sum(1 for line in (proc.stdout or "").splitlines() if ": error:" in line)
    st = "pass" if proc.returncode == 0 else "warn"
    return {"status": st, "exit_code": proc.returncode, "errors": errors}


def _semgrep_rules_dir() -> Path | None:
    primary = MAIL_ROOT / "config" / "review" / "semgrep"
    if primary.is_dir():
        return primary
    legacy = MAIL_ROOT / "semgrep-rules"
    return legacy if legacy.is_dir() else None


def _run_semgrep(repo: Path) -> dict:
    if not shutil.which("semgrep"):
        return {"status": "skip", "reason": "semgrep not found"}
    rules = _semgrep_rules_dir()
    if rules is None:
        return {"status": "skip", "reason": "semgrep rules dir not found"}
    try:
        proc = subprocess.run(
            ["semgrep", "scan", "--config", str(rules), "--json", str(repo)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}
    if proc.returncode not in (0, 1):
        return {"status": "error", "exit_code": proc.returncode}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "error", "error": "invalid semgrep json"}
    results = data.get("results") or []
    rules_hit = sorted({str(r.get("check_id", "")) for r in results if r.get("check_id")})
    findings = len(results)
    st = "pass" if findings == 0 else "warn"
    return {
        "status": st,
        "findings": findings,
        "blocking": False,
        "rules_hit": rules_hit,
    }


def run_static_analysis(
    repo: Path,
    *,
    pylint: bool = False,
    mypy: bool = False,
    semgrep: bool = False,
) -> dict:
    if not (pylint or mypy or semgrep):
        return {"status": "skip"}
    py_files = _changed_py_files(repo)
    parts: dict = {}
    statuses: list[str] = []
    if pylint:
        parts["pylint"] = _run_pylint(repo, py_files)
        statuses.append(parts["pylint"]["status"])
    if mypy:
        parts["mypy"] = _run_mypy(repo, py_files)
        statuses.append(parts["mypy"]["status"])
    if semgrep:
        parts["semgrep"] = _run_semgrep(repo)
        statuses.append(parts["semgrep"]["status"])
    layer: dict = {"status": _merge_status(*statuses) if statuses else "skip", "tools": parts}
    if "pylint" in parts and parts["pylint"].get("score") is not None:
        layer["pylint_score"] = parts["pylint"]["score"]
    if "mypy" in parts and "errors" in parts["mypy"]:
        layer["mypy_errors"] = parts["mypy"]["errors"]
    if "semgrep" in parts and parts["semgrep"].get("status") != "skip":
        layer["semgrep"] = {
            k: parts["semgrep"][k]
            for k in ("findings", "blocking", "rules_hit")
            if k in parts["semgrep"]
        }
    return layer


def _resolve_review_script(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    env = os.environ.get("MAILBUS_REVIEW_SCRIPT", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    candidate = MAIL_ROOT.parent / "pr-agent" / "review.py"
    return candidate if candidate.is_file() else None


def _parse_review_verdict(text: str) -> str:
    if "🔴" in text or "严重" in text:
        return "request_changes"
    if "🟡" in text or "一般" in text:
        return "comment"
    if "✓ 没有代码变更" in text or "没有代码变更" in text:
        return "no_changes"
    return "approve"


def run_ai_review(
    repo: Path,
    *,
    commit_sha: str,
    review_script: Path | None = None,
    report_dir: Path | None = None,
) -> tuple[dict, list[dict]]:
    script = review_script or _resolve_review_script()
    if script is None:
        return {"status": "skip", "reason": "review.py not found"}, []
    short = commit_sha[:7]
    out_md = (report_dir or repo / "store" / "reports") / f"{short}.diff-review.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--commit", "HEAD", "--output", str(out_md)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "reviewer_tool": script.name, "error": str(exc)}, []
    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return {
            "status": "error",
            "reviewer_tool": script.name,
            "exit_code": proc.returncode,
            "summary": combined.strip()[:500] or None,
        }, []
    summary = ""
    if out_md.is_file():
        body = out_md.read_text(encoding="utf-8", errors="replace")
        summary = body.strip().splitlines()[0][:200] if body.strip() else ""
        verdict = _parse_review_verdict(body)
    else:
        verdict = _parse_review_verdict(combined)
    if verdict == "no_changes":
        return {"status": "skip", "reviewer_tool": script.name, "verdict": verdict}, []
    layer = {
        "status": "done",
        "reviewer_tool": script.name,
        "verdict": verdict,
    }
    if summary:
        layer["summary"] = summary
    stat = _git(["diff", "--shortstat", "HEAD~1..HEAD"], repo)
    if stat:
        m = re.search(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?", stat)
        if m:
            layer["diff_stat"] = {
                "files": int(m.group(1)),
                "insertions": int(m.group(2) or 0),
                "deletions": int(m.group(3) or 0),
            }
    try:
        rel = out_md.relative_to(repo)
    except ValueError:
        rel = out_md
    artifacts = [{"kind": "file", "path": str(rel).replace("\\", "/"), "label": "AI review 全文"}]
    return layer, artifacts


def build_report(
    repo: Path,
    *,
    author_agent: str = "unknown",
    pytest_layer: dict | None = None,
    static_layer: dict | None = None,
    ai_layer: dict | None = None,
    extra_artifacts: list[dict] | None = None,
    apply_baseline: bool = True,
) -> dict:
    sha = _git(["rev-parse", "HEAD"], repo) or "0" * 40
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo) or "unknown"
    regression = pytest_layer if pytest_layer is not None else _run_pytest(repo)
    if apply_baseline and regression.get("pytest") is not None:
        _apply_baseline_comparison(regression, repo)
    static_analysis = static_layer if static_layer is not None else {"status": "skip"}
    ai_review = ai_layer if ai_layer is not None else {"status": "skip"}
    aggregate = _merge_status(
        regression.get("status", "pass"),
        static_analysis.get("status", "skip"),
        ai_review.get("status", "skip"),
    )
    artifacts = list(extra_artifacts or [])
    return {
        "schema": "code-review-report-v1",
        "commit_sha": sha,
        "repo": {
            "name": repo.name,
            "root": str(repo.resolve()),
            "branch": branch,
        },
        "author_agent": author_agent,
        "trigger": "post-commit-harness",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "layers": {
            "regression": regression,
            "static_analysis": static_analysis,
            "ai_review": ai_review,
        },
        "aggregate_status": aggregate,
        "blocking": aggregate == "fail",
        "artifacts": artifacts,
        "mailbus": {"trusted_source": "post-commit-harness"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate code-review-report-v1 JSON")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="git repo root")
    ap.add_argument("--out", type=Path, help="output path (default: store/reports/{sha}.json)")
    ap.add_argument("--author-agent", default="unknown")
    ap.add_argument("--skip-pytest", action="store_true")
    ap.add_argument(
        "--static-analysis",
        action="store_true",
        help="enable pylint + mypy + semgrep (each skipped if tool missing)",
    )
    ap.add_argument("--pylint", action="store_true", help="run pylint on changed .py files")
    ap.add_argument("--mypy", action="store_true", help="run mypy on changed .py files")
    ap.add_argument("--semgrep", action="store_true", help="run semgrep security scan")
    ap.add_argument("--run-ai-review", action="store_true", help="run review.py AI diff review")
    ap.add_argument("--review-script", type=Path, help="override path to review.py")
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="write current pytest failures to store/reports/baseline.json",
    )
    args = ap.parse_args()

    repo = args.repo.resolve()
    if args.update_baseline:
        layer = _run_pytest(repo)
        failed = layer.get("pytest", {}).get("failed_nodeids") or []
        path = _write_baseline(repo, failed)
        print(f"updated baseline {path} ({len(failed)} known failures)")
        if not args.out and not args.skip_pytest and not args.static_analysis and not args.run_ai_review:
            return 0
    pytest_layer = {"status": "skip", "pytest": {"new_failures_vs_baseline": []}} if args.skip_pytest else None
    use_pylint = args.pylint or args.static_analysis
    use_mypy = args.mypy or args.static_analysis
    use_semgrep = args.semgrep or args.static_analysis
    static_layer = (
        run_static_analysis(repo, pylint=use_pylint, mypy=use_mypy, semgrep=use_semgrep)
        if (use_pylint or use_mypy or use_semgrep)
        else None
    )
    ai_layer = None
    extra_artifacts: list[dict] = []
    if args.run_ai_review:
        sha = _git(["rev-parse", "HEAD"], repo) or "0" * 40
        script = _resolve_review_script(str(args.review_script) if args.review_script else None)
        ai_layer, extra_artifacts = run_ai_review(
            repo,
            commit_sha=sha,
            review_script=script,
            report_dir=repo / "store" / "reports",
        )
    report = build_report(
        repo,
        author_agent=args.author_agent,
        pytest_layer=pytest_layer,
        static_layer=static_layer,
        ai_layer=ai_layer,
        extra_artifacts=extra_artifacts,
    )
    sha = report["commit_sha"]
    out = args.out or (repo / "store" / "reports" / f"{sha}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} aggregate_status={report['aggregate_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
