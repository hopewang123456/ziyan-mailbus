#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER="${HERMES_CONTAINER:-docker-agents-hermes-1}"
SCRIPT_HOST="${SCRIPT_DIR}/install-memos-in-container.sh"

docker cp "$SCRIPT_HOST" "$CONTAINER:/tmp/install-memos-in-container.sh"
docker exec -u root "$CONTAINER" bash /tmp/install-memos-in-container.sh

# Ensure every profile uses memtensor provider (AM stays MCP-only)
docker exec -u root "$CONTAINER" python3 <<'PY'
from pathlib import Path
import re
root = Path("/home/hermes/.hermes")
paths = [root / "config.yaml"]
paths += sorted((root / "profiles").glob("*/config.yaml"))
for p in paths:
    if not p.is_file():
        continue
    text = p.read_text(encoding="utf-8")
    orig = text
    if "memory:" in text and "provider:" not in text.split("memory:", 1)[-1].split("\n\n", 1)[0]:
        text = re.sub(r"(memory:\s*\n)", r"\1  provider: memtensor\n", text, count=1)
    elif re.search(r"(?m)^\s*provider:\s*", text) is None and "memory:" in text:
        text = re.sub(r"(memory:\s*\n)", r"\1  provider: memtensor\n", text, count=1)
    if text != orig:
        p.write_text(text, encoding="utf-8")
        print("updated", p)
PY
