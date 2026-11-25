"""出站 endpoint 的 SSRF 防护：只允许 http(s)，阻断云元数据与本地特殊地址。"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse

from mailbus.core.shared.errors import UnprocessableError

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_METADATA_HOSTS = frozenset({
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
})
_METADATA_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
})


def validate_endpoint(endpoint: str) -> str:
    """校验并返回规范化 endpoint；不合法抛 422。"""
    text = (endpoint or "").strip()
    if not text:
        raise UnprocessableError("endpoint 不能为空")
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError as exc:
        raise UnprocessableError("endpoint 不是合法 URL") from exc
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnprocessableError("endpoint 仅支持 http/https")
    if not parsed.hostname:
        raise UnprocessableError("endpoint 缺少主机")
    if parsed.username or parsed.password:
        raise UnprocessableError("endpoint 不允许携带用户信息")
    host = parsed.hostname.strip().lower().rstrip(".")
    if host in _METADATA_HOSTS or host.endswith(".internal"):
        raise UnprocessableError("endpoint 指向云元数据或内部域名，已拒绝")
    for address in _addresses(host):
        if not _allowed_address(address):
            raise UnprocessableError("endpoint 指向受限地址，已拒绝")
    return text


def _addresses(host: str):
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    values = []
    for info in infos:
        try:
            values.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return values


def _allowed_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address in _METADATA_IPS:
        return False
    return not (
        address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )
