"""Fail if committed tree looks like it contains live secrets / private team paths.

Scans git-tracked text files only (not store/, .env). Prefer examples + gitignore
over encrypting secrets into the repo.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# High-confidence secret material (not model names / env var *names* in code)
SECRET_RES = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----"),
    # live assignment with a long literal (skip empty / ${ENV} / get("KEY",""))
    re.compile(
        r"(?i)(?:openai|anthropic|deepseek)_api_key\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
    ),
]

# Should stay untracked (team-private); if still in index, fail
FORBIDDEN_TRACKED_PREFIXES = (
    "access/transport/dali/",
    "access/transport/ling",  # lingyun/lingzhao/...
    "access/transport/xiaoqi/",
    "access/transport/yige/",
)


def _tracked_files() -> list[str]:
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.decode("utf-8", errors="replace").split("\0") if p]


class TestNoSecretsInGitTree(unittest.TestCase):
    def test_private_team_paths_untracked(self) -> None:
        tracked = _tracked_files()
        if not tracked:
            self.skipTest("not a git checkout or empty index")
        bad: list[str] = []
        for path in tracked:
            if path == "config/mailbus/launch-ports.json":
                bad.append(path)
                continue
            if path.startswith("config/agents/") and path.endswith(".override.json"):
                bad.append(path)
                continue
            for prefix in FORBIDDEN_TRACKED_PREFIXES:
                if path.startswith(prefix):
                    bad.append(path)
                    break
        self.assertEqual(bad, [], msg="untrack private files (keep local); use *.example.json:\n" + "\n".join(bad))

    def test_no_high_confidence_secrets_in_tracked_text(self) -> None:
        tracked = _tracked_files()
        if not tracked:
            self.skipTest("not a git checkout or empty index")
        hits: list[str] = []
        exts = {".py", ".json", ".yml", ".yaml", ".md", ".txt", ".toml", ".env", ".sh", ".ps1", ".bat"}
        for rel in tracked:
            p = ROOT / rel
            if p.suffix.lower() not in exts and not rel.endswith(".example"):
                continue
            if "node_modules" in rel or rel.endswith("package-lock.json"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for rx in SECRET_RES:
                if rx.search(text):
                    hits.append(f"{rel}: {rx.pattern}")
                    break
        self.assertEqual(hits, [], msg="possible secrets in tracked files:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
