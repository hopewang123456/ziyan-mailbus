"""包装 tools/validate-examples.py — store/examples JSON 结构校验。"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_VALIDATE_PATH = os.path.join(ROOT, "tools", "validate-examples.py")
_spec = importlib.util.spec_from_file_location("validate_examples", _VALIDATE_PATH)
assert _spec and _spec.loader
_ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ve)
validate_file = _ve.validate_file
_load = _ve._load


class TestValidateExamples(unittest.TestCase):
    def test_cli_all_examples_ok(self):
        proc = subprocess.run(
            [sys.executable, _VALIDATE_PATH],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("ALL EXAMPLES OK", proc.stdout)

    def test_golden_a2a_path_a_valid(self):
        reg = _load(_ve.REGISTRY)
        roles = _load(_ve.ROLE_TYPES)
        known_roles = {int(k) for k in roles.get("roles", {})}
        path = os.path.join(ROOT, "store", "examples", "golden-a2a-path-a.json")
        if not os.path.isfile(path):
            self.skipTest("golden-a2a-path-a.json missing")
        errs = validate_file(_ve.Path(path), reg, known_roles)
        self.assertEqual(errs, [], msg=errs)

    def test_code_review_report_example_valid(self):
        reg = _load(_ve.REGISTRY)
        roles = _load(_ve.ROLE_TYPES)
        known_roles = {int(k) for k in roles.get("roles", {})}
        path = os.path.join(ROOT, "store", "examples", "code-review-report.example.json")
        if not os.path.isfile(path):
            self.skipTest("code-review-report.example.json missing")
        errs = validate_file(_ve.Path(path), reg, known_roles)
        self.assertEqual(errs, [], msg=errs)


if __name__ == "__main__":
    unittest.main()
