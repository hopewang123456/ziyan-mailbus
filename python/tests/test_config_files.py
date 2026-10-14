"""config_files: runtime binds non-example paths only."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.adapters.config.config_files import (
    example_sibling,
    is_example_config_name,
    iter_runtime_json_files,
    materialize_from_example,
    resolve_config_path,
)


class TestConfigFiles(unittest.TestCase):
    def test_is_example_name(self) -> None:
        self.assertTrue(is_example_config_name("launch-ports.example.json"))
        self.assertTrue(is_example_config_name("coder.override.example.json"))
        self.assertTrue(is_example_config_name("transport.template.json"))
        self.assertFalse(is_example_config_name("launch-ports.json"))
        self.assertFalse(is_example_config_name("agent-h.override.json"))

    def test_resolve_prefers_real_never_example(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "foo.json"
            ex = root / "foo.example.json"
            ex.write_text('{"from":"example"}', encoding="utf-8")
            real.write_text('{"from":"real"}', encoding="utf-8")
            res = resolve_config_path(real)
            self.assertEqual(res.path, real)
            self.assertFalse(str(res.path).endswith(".example.json"))

    def test_resolve_missing_does_not_return_example(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "foo.json"
            ex = root / "foo.example.json"
            ex.write_text("{}", encoding="utf-8")
            res = resolve_config_path(real)
            self.assertIsNone(res.path)
            self.assertIn("copy", res.hint.lower())
            self.assertIn("foo.example.json", res.hint)

    def test_resolve_rejects_example_path(self) -> None:
        with self.assertRaises(ValueError):
            resolve_config_path(Path("x.example.json"))

    def test_materialize_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "foo.json"
            ex = root / "foo.example.json"
            ex.write_text('{"v":1}', encoding="utf-8")
            real.write_text('{"v":9}', encoding="utf-8")
            materialize_from_example(real)
            self.assertEqual(real.read_text(encoding="utf-8"), '{"v":9}')

    def test_materialize_creates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "foo.json"
            ex = root / "foo.example.json"
            ex.write_text('{"v":1}', encoding="utf-8")
            out = materialize_from_example(real)
            self.assertEqual(out, real)
            self.assertTrue(real.is_file())

    def test_iter_skips_examples(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.json").write_text("{}", encoding="utf-8")
            (root / "b.example.json").write_text("{}", encoding="utf-8")
            (root / "c.override.example.json").write_text("{}", encoding="utf-8")
            (root / "d.override.json").write_text("{}", encoding="utf-8")
            names = {p.name for p in iter_runtime_json_files(root)}
            self.assertEqual(names, {"a.json", "d.override.json"})

    def test_example_sibling(self) -> None:
        self.assertEqual(
            example_sibling(Path("/x/launch-ports.json")),
            Path("/x/launch-ports.example.json"),
        )


if __name__ == "__main__":
    unittest.main()
