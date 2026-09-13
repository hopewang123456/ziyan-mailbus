"""compose_files 文件柜：list/read/write，禁 path escape，无启停。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.adapters.config.compose_files import (
    list_compose_files,
    read_compose_file,
    write_compose_file,
)


class TestComposeFiles(unittest.TestCase):
    def test_roundtrip_under_docker_agents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            da = root / "docker-agents"
            da.mkdir()
            write_compose_file(root, "docker-agents/docker-compose.demo.yml", "services:\n  x: {}\n")
            files = list_compose_files(root)
            self.assertTrue(any(f["path"].endswith("docker-compose.demo.yml") for f in files))
            got = read_compose_file(root, "docker-agents/docker-compose.demo.yml")
            self.assertIn("services:", got["content"])

    def test_reject_path_escape(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                read_compose_file(td, "../secrets.yml")


if __name__ == "__main__":
    unittest.main()
