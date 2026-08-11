"""Gate: lib code must not bind *.example.json as the primary config path."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lib"

# Allowlisted modules may mention .example.json (materialize / docs / hints only)
ALLOW_FILES = {
    "config_files.py",
}

# String literals ending with .example.json that look like open/join targets
LITERAL_RE = re.compile(r".+\.example\.json$")


class TestConfigReadersNoExample(unittest.TestCase):
    def test_no_example_json_string_literals_as_paths(self) -> None:
        bad: list[str] = []
        for path in ROOT.rglob("*.py"):
            if path.name in ALLOW_FILES:
                continue
            src = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src, filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                val = node.value.replace("\\", "/")
                if not LITERAL_RE.match(val):
                    continue
                # Allow mention in long hint messages that also contain "copy"
                line = src.splitlines()[node.lineno - 1] if node.lineno else ""
                if "copy" in line.lower() or "hint" in line.lower():
                    continue
                if "example" in line and ("copy" in src[max(0, node.col_offset - 80) : node.col_offset + 80].lower()):
                    continue
                bad.append(f"{path.relative_to(ROOT.parent)}:{node.lineno}:{val}")
        self.assertEqual(
            bad,
            [],
            msg="runtime must bind non-example paths; move example refs to config_files/materialize:\n"
            + "\n".join(bad),
        )


if __name__ == "__main__":
    unittest.main()
