"""技能包来源探测：只读元信息，不复制、不安装、不执行。"""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from mailbus.core.skills.models import SkillProbe
from mailbus.core.skills.values import SkillSourceType

_MAX_BYTES = 65536
_MAX_VERSION_LINES = 40
_TIMEOUT_SEC = 5.0

_VERSION_KEYS = frozenset({"version", "skill_version"})
_ALLOWED_HTTP_SCHEMES = frozenset({"http", "https"})
# L7：阻断本机 / 链路本地（含云元数据 169.254.169.254），允许企业私网来源。
_BLOCKED_V4 = tuple(
    ipaddress.ip_network(net) for net in ("0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16")
)
_BLOCKED_V6 = tuple(
    ipaddress.ip_network(net) for net in ("::1/128", "fe80::/10")
)


class SkillSource:
    """按来源类型分派：local 读本地目录/文件，http 读取入口内容。"""

    def probe(
        self, source_type: SkillSourceType, source_uri: str, entry: str
    ) -> SkillProbe:
        try:
            if source_type is SkillSourceType.LOCAL:
                return self._local(source_uri, entry)
            return self._http(source_uri)
        except Exception as exc:  # 探测失败只记录，不影响台账写入
            message = str(exc).strip() or type(exc).__name__
            return SkillProbe(False, error=message[:200])

    @staticmethod
    def _local(source_uri: str, entry: str) -> SkillProbe:
        base = Path(source_uri).expanduser().resolve()
        if not base.exists():
            return SkillProbe(False, error="来源路径不存在")
        root = base if base.is_dir() else base.parent
        # L7：入口不得逃逸来源目录（阻断 ../ 与绝对路径穿越）。
        target = (root / entry).resolve()
        if not target.is_relative_to(root):
            return SkillProbe(False, error="入口路径超出来源目录")
        if not target.is_file():
            return SkillProbe(False, error=f"入口文件不存在：{entry}")
        text = target.read_text(encoding="utf-8", errors="replace")[:_MAX_BYTES]
        return SkillProbe(True, version=_version_of(text))

    @staticmethod
    def _http(source_uri: str) -> SkillProbe:
        # L7：仅允许 http/https，避免 file:// 等 scheme 读取本地或内网资源。
        parsed = urlparse(source_uri)
        if parsed.scheme.lower() not in _ALLOWED_HTTP_SCHEMES:
            return SkillProbe(False, error="技能来源仅支持 http/https")
        if not parsed.hostname:
            return SkillProbe(False, error="技能来源缺少主机名")
        if _blocked_host(parsed.hostname):
            return SkillProbe(False, error="技能来源地址不允许（本机或链路本地）")
        request = urllib.request.Request(
            source_uri, headers={"User-Agent": "mailbus-skill-probe"}
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                return SkillProbe(False, error=f"HTTP {status}")
            text = response.read(_MAX_BYTES).decode("utf-8", errors="replace")
        return SkillProbe(True, version=_version_of(text))


def _blocked_host(host: str) -> bool:
    """解析主机名，命中本机/链路本地网段则拒绝。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # 解析失败交给后续请求报错
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        nets = _BLOCKED_V4 if ip.version == 4 else _BLOCKED_V6
        if any(ip in net for net in nets):
            return True
    return False


def _version_of(text: str) -> str:
    """从入口文件前若干行读取 version: 字段（兼容 YAML frontmatter）。"""
    for line in text.splitlines()[:_MAX_VERSION_LINES]:
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in _VERSION_KEYS:
            return value.strip().strip("\"'")
    return ""
