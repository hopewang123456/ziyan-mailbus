#!/usr/bin/env python3
"""One-shot: docker-agents/*.sh 9812 → MAILBUS_API_PORT (default 9814)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DA = ROOT / "docker-agents"
API_SOURCE = '. "${SCRIPT_DIR}/lib/api-url.sh"'

SUBMIT_SCRIPTS = [
    "workflow-smoke.sh",
    "submit-game-stellar-v3-live-docker.sh",
    "submit-game-stellar-task.sh",
    "submit-scheduler-validation-task.sh",
    "submit-hardening-task.sh",
    "pre-v3-readiness.sh",
    "monitor-regression.sh",
    "watch-scheduler-iteration.sh",
    "task-flow-snapshot.sh",
    "watch-pipeline.sh",
    "check-workflow.sh",
    "watch-workflow.sh",
    "stability-test.sh",
]

COMPOSE_SCRIPTS = ["start-team.sh", "e2e-test.sh", "smoke-test.sh", "mailbus-pipeline-e2e.sh"]


def _ensure_api_source(text: str, script_dir_var: str = "SCRIPT_DIR") -> str:
    if "lib/api-url.sh" in text:
        return text
    marker = f'{script_dir_var}="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"'
    alt = f'{script_dir_var}="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"'
    for m in (marker, f'COMPOSE_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"'):
        if m in text:
            insert = f'{m}\n{API_SOURCE.replace("SCRIPT_DIR", script_dir_var if "COMPOSE" not in m else "COMPOSE_DIR")}\n'
            return text.replace(m, insert, 1)
    # fallback after set -e line
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines[:8]):
        if line.startswith("set "):
            lines.insert(i + 1, f'\nSCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"\n{API_SOURCE}\n')
            return "".join(lines)
    return text


def patch_submit_style(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "9812" not in text and "MAILBUS_API_BASE" in text:
        return False
    orig = text
    text = _ensure_api_source(text)
    text = re.sub(
        r'BASE="http://127\.0\.0\.1:9812"',
        'BASE="$MAILBUS_API_BASE"',
        text,
    )
    text = text.replace("http://127.0.0.1:9812", '"$MAILBUS_API_BASE"')
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_compose_style(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    var = "COMPOSE_DIR" if "COMPOSE_DIR=" in text else "SCRIPT_DIR"
    text = _ensure_api_source(text, var)
    text = text.replace(":9812 ", ":${MAILBUS_API_PORT} ")
    text = text.replace(":9812/", ":${MAILBUS_API_PORT}/")
    text = text.replace(":9812'", ":${MAILBUS_API_PORT}'")
    text = text.replace("localhost:9812", "localhost:${MAILBUS_API_PORT}")
    text = text.replace("127.0.0.1:9812", "127.0.0.1:${MAILBUS_API_PORT}")
    text = text.replace("win9812", "win_api")
    text = text.replace("wsl9812", "wsl_api")
    text = text.replace("code9812", "code_api")
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_mailbus_boot(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    if "MAILBUS_API_PORT" not in text:
        text = text.replace(
            'CONFIG_PATH="$STORE_DIR/config.json"\n',
            'CONFIG_PATH="$STORE_DIR/config.json"\nMAILBUS_API_PORT="${MAILBUS_API_PORT:-9814}"\n',
        )
    text = text.replace("--port 9812", "--port ${MAILBUS_API_PORT}")
    text = text.replace("(:9812)", "(:${MAILBUS_API_PORT})")
    text = text.replace("ports+=(9812)", "ports+=(${MAILBUS_API_PORT})")
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    for name in SUBMIT_SCRIPTS:
        p = DA / name
        if p.is_file() and patch_submit_style(p):
            changed.append(str(p))
    for name in COMPOSE_SCRIPTS:
        p = DA / name
        if p.is_file() and patch_compose_style(p):
            changed.append(str(p))
    boot = ROOT / "mailbus-boot.sh"
    if boot.is_file() and patch_mailbus_boot(boot):
        changed.append(str(boot))
    print(f"patched {len(changed)} files")
    for c in changed:
        print(f"  {c}")


if __name__ == "__main__":
    main()
