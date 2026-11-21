"""G9 部署形态守卫：mailbus 不得依赖 Docker，避免容器化成为运行前提。

约束来源：mailbus 是可独立部署的服务（Windows/Linux 原生或容器皆可）。
- 不得挂载 /var/run/docker.sock（等于把宿主 Docker 控制权交给容器）
- 镜像不得安装 docker CLI（只有操纵 Docker 才需要）
投递通道是 A2A / file_bus，均不需要 Docker socket。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import REPO_ROOT  # noqa: E402

COMPOSE_DIR = REPO_ROOT / "shared" / "docker-agents"
COMPOSE_FILES = [
    COMPOSE_DIR / "docker-compose.yml",
    COMPOSE_DIR / "compose.public.yml",
]
DOCKERFILE = COMPOSE_DIR / "mailbus" / "Dockerfile"


def _existing(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.is_file()]


def test_compose_does_not_mount_docker_sock() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _existing(COMPOSE_FILES)
        if "docker.sock" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "compose 文件挂载了 docker.sock（容器将获得宿主 Docker 控制权）："
        + ", ".join(offenders)
    )


def test_image_does_not_install_docker_cli() -> None:
    if not DOCKERFILE.is_file():
        return
    text = DOCKERFILE.read_text(encoding="utf-8")
    for marker in ("download.docker.com", "/usr/local/bin/docker"):
        assert marker not in text, f"{DOCKERFILE.name} 仍安装 docker CLI：{marker}"
