"""W7e: application must not call datetime.now / time.time directly — use lib.infra.clock."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lib" / "application"

# Attribute calls that bypass ClockPort / adapters.clock
FORBIDDEN_ATTR = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("time", "time"),
}


def _offenders(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            key = (func.value.id, func.attr)
            if key in FORBIDDEN_ATTR:
                hits.append(f"{path.as_posix()}:{node.lineno}:{func.value.id}.{func.attr}()")
    return hits


class TestApplicationClockLint(unittest.TestCase):
    def test_application_no_raw_datetime_or_time_time(self) -> None:
        if not ROOT.is_dir():
            self.skipTest("no application package")
        bad: list[str] = []
        for path in ROOT.rglob("*.py"):
            bad.extend(_offenders(path))
        self.assertEqual(bad, [], msg="use lib.infra.clock; offenders:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
