"""lib.api._port_occupied 的端口占用检测（host:port 粒度，含地址归一化）。"""

import socket
import threading

import pytest

from lib.api import _port_occupied


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_listener(host: str, port: int) -> socket.socket:
    """绑定并监听 host:port，后台持续 accept 以排空 backlog（模拟真实 HTTP 服务器）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(16)

    def _accept_loop() -> None:
        while True:
            try:
                conn, _ = s.accept()
                conn.close()
            except OSError:
                return

    threading.Thread(target=_accept_loop, daemon=True).start()
    return s


def test_free_port_not_occupied():
    port = _free_port()
    assert _port_occupied("127.0.0.1", port) is False
    assert _port_occupied("localhost", port) is False
    assert _port_occupied("0.0.0.0", port) is False


def test_loopback_aliases_are_equivalent():
    """127.0.0.1 / localhost / 0.0.0.0 通配均应识别回环占用。"""
    port = _free_port()
    srv = _start_listener("127.0.0.1", port)
    try:
        assert _port_occupied("127.0.0.1", port) is True
        assert _port_occupied("localhost", port) is True
        # 0.0.0.0 通配会覆盖回环，判占用
        assert _port_occupied("0.0.0.0", port) is True
    finally:
        srv.close()


def test_external_ip_conflicts_only_with_wildcard():
    """绑定具体非回环 IP：通配 0.0.0.0 应判占用；回环不冲突。"""
    resolved = socket.gethostbyname_ex(socket.gethostname())[2]
    nonloop = [ip for ip in resolved if not ip.startswith("127.") and ":" not in ip]
    if not nonloop:
        pytest.skip("no non-loopback IPv4 available")
    ip = nonloop[0]
    port = _free_port()
    try:
        srv = _start_listener(ip, port)
    except OSError:
        pytest.skip(f"cannot bind {ip}:{port}")
    try:
        assert _port_occupied(ip, port) is True
        # 通配绑定会与该网卡冲突
        assert _port_occupied("0.0.0.0", port) is True
        # 回环未被占用，具体探测回环应判未冲突
        assert _port_occupied("127.0.0.1", port) is False
    finally:
        srv.close()
