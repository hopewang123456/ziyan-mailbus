"""Tests for docker CLI bridge detection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from lib.adapters.plane.platform_runner import (
    docker_cli_bridge_available,
    docker_sock_available,
    running_in_mailbus_docker,
)


class DockerCliBridgeTest(unittest.TestCase):
    @patch("lib.adapters.plane.platform_runner.os.path.exists", return_value=True)
    def test_docker_sock_not_isfile(self, _exists) -> None:
        self.assertTrue(docker_sock_available())

    @patch("lib.adapters.plane.platform_runner.os.path.isfile")
    @patch("lib.adapters.plane.platform_runner.os.path.isdir")
    @patch("lib.adapters.plane.platform_runner.os.path.exists")
    def test_bridge_when_sock_exists(self, mock_exists, mock_isdir, mock_isfile) -> None:
        mock_exists.return_value = True
        mock_isdir.return_value = False
        mock_isfile.return_value = False
        self.assertTrue(docker_cli_bridge_available())

    @patch("lib.adapters.plane.platform_runner.os.path.isfile", return_value=True)
    @patch("lib.adapters.plane.platform_runner.os.path.isdir", return_value=True)
    @patch("lib.adapters.plane.platform_runner.os.path.exists", return_value=False)
    def test_running_in_mailbus_docker(self, _exists, _isdir, isfile) -> None:
        def side(path: str) -> bool:
            return path == "/.dockerenv"

        isfile.side_effect = side
        self.assertTrue(running_in_mailbus_docker())


if __name__ == "__main__":
    unittest.main()
