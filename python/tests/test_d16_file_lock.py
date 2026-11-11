"""D16 批1：跨进程文件锁（双栈 SoT 统一地基）。

覆盖：锁根解析（默认 <data_dir>/.locks、MAILBUS_LOCK_DIR 覆盖）、
锁路径规范化、进程内多线程互斥、跨进程三方对打、锁文件常驻
（不 unlink，防 inode 竞态）、同线程重入豁免。
对应 java 侧 CrossProcessFileLockTest（同 hash 规则对打）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading

import pytest

from lib.infra import utils
from lib.infra.utils import file_lock, json_read, json_write

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_BUMP_CHILD = textwrap.dedent(
    """
    import sys, os
    sys.path.insert(0, sys.argv[2])
    from lib.infra.utils import file_lock, json_read, json_write
    f = sys.argv[1]
    for _ in range(int(sys.argv[3])):
        with file_lock(path=f):
            cur = json_read(f, default={"a": 0}, ttl=0)
            cur["a"] = cur.get("a", 0) + 1
            json_write(f, cur)
    """
)


@pytest.fixture
def lock_env(tmp_path, monkeypatch):
    """锁根指向临时目录，测试完还原（monkeypatch 自动还原 env）。"""
    monkeypatch.setenv("MAILBUS_LOCK_DIR", str(tmp_path / ".locks"))
    utils.reset_lock_root_cache()
    yield tmp_path / ".locks"
    utils.reset_lock_root_cache()


def test_lock_root_env_override(lock_env):
    """MAILBUS_LOCK_DIR 显式覆盖锁根。"""
    assert utils.get_lock_root() == str(lock_env)


def test_lock_root_defaults_to_data_dir(tmp_path, monkeypatch):
    """默认锁根 = <data_dir>/.locks（随数据走共享卷，D16 双栈互斥前提）。

    DEFAULT_DATA_DIR 在 constants import 时固化，运行时只能 patch 模块属性。
    """
    monkeypatch.delenv("MAILBUS_LOCK_DIR", raising=False)
    monkeypatch.setattr("lib.infra.constants.DEFAULT_DATA_DIR", str(tmp_path))
    utils.reset_lock_root_cache()
    try:
        assert utils.get_lock_root() == str(tmp_path / ".locks")
    finally:
        utils.reset_lock_root_cache()


def test_lock_path_normalized(lock_env, tmp_path):
    """规范化规则：绝对路径 + normpath 后 sha256 前 16 位（java 侧逐字节一致）。"""
    raw = str(tmp_path / "a.json")
    variants = [raw, raw.replace("\\", "/")]
    if not raw.startswith("\\\\"):  # 非 UNC 路径可加 . 显式段
        variants.append(os.path.join(str(tmp_path), ".", "a.json"))
    p1 = utils._lock_path(raw)
    for v in variants:
        assert utils._lock_path(v) == p1, f"同一目标文件的路径变体必须命中同一锁文件: {v}"
    assert os.path.basename(p1).startswith("mailbus-") and p1.endswith(".lock")


def test_lock_file_not_unlinked(lock_env, tmp_path):
    """D16 批1：锁文件常驻（跨进程 unlink 有 inode 竞态，stale 无害）。"""
    target = tmp_path / "keep.json"
    json_write(str(target), {"a": 1})
    lock_file = utils._lock_path(str(target))
    assert os.path.exists(lock_file), "锁文件应在使用后常驻"


def test_intra_process_thread_mutex(lock_env, tmp_path):
    """进程内多线程互斥：并发读改写计数必须精确（lockf 语义下线程锁先行）。"""
    target = str(tmp_path / "count.json")
    json_write(target, {"a": 0})

    def bump(n: int) -> None:
        for _ in range(n):
            with file_lock(path=target):
                cur = json_read(target, default={"a": 0}, ttl=0)
                cur["a"] = cur.get("a", 0) + 1
                json_write(target, cur)

    threads = [threading.Thread(target=bump, args=(100,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert json_read(target, ttl=0)["a"] == 400


def test_cross_process_mutex(lock_env, tmp_path):
    """跨进程三方对打：两个子进程 + 本进程并发读改写，计数精确无丢失。"""
    target = str(tmp_path / "count.json")
    json_write(target, {"a": 0})
    script = tmp_path / "bump_child.py"
    script.write_text(_BUMP_CHILD, encoding="utf-8")
    root = os.path.dirname(TESTS_DIR)
    env = dict(os.environ)
    # 子进程继承 monkeypatch 后的 MAILBUS_LOCK_DIR → 三方同一锁根
    children = [
        subprocess.Popen([sys.executable, str(script), target, root, "80"])
        for _ in range(2)
    ]
    for _ in range(40):
        with file_lock(path=target):
            cur = json_read(target, default={"a": 0}, ttl=0)
            cur["a"] = cur.get("a", 0) + 1
            json_write(target, cur)
    for c in children:
        assert c.wait(timeout=60) == 0
    assert json_read(target, ttl=0)["a"] == 200


def test_same_thread_reentrant(lock_env, tmp_path):
    """同线程重入：外层持锁后嵌套 json_write（自带锁）不自我死锁。"""
    target = str(tmp_path / "re.json")
    json_write(target, {"a": 1})
    with file_lock(path=target):
        json_write(target, {"a": 2})  # json_write 内部再拿同一把锁 → 豁免通过
    assert json_read(target, ttl=0)["a"] == 2


def test_lock_hash_matches_java_contract(lock_env, tmp_path):
    """锁名 hash 契约锁定：sha256(_store_relative_key)[:16]，改动即破坏双栈互斥。

    键规则：data_dir 内目标用相对路径（双栈容器内挂载路径不同仍能命中），
    data_dir 外退回绝对路径；统一正斜杠；Windows 统一小写。
    """
    import hashlib

    # data_dir 内目标 → 相对键
    from lib.infra import constants

    store = tmp_path / "store"
    store.mkdir()
    monkey_target = str(store / "inbox" / "a" / "inbox.json")
    orig = constants.DEFAULT_DATA_DIR
    constants.DEFAULT_DATA_DIR = str(store)
    try:
        key = "inbox/a/inbox.json"
        if sys.platform == "win32":
            key = key.lower()
        expect = "mailbus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] + ".lock"
        assert os.path.basename(utils._lock_path(monkey_target)) == expect
    finally:
        constants.DEFAULT_DATA_DIR = orig
    # data_dir 外目标（跨盘/临时目录）→ 绝对路径键（正斜杠 + win 小写）
    norm = os.path.normpath(os.path.abspath(str(tmp_path / "outside.json")))
    key2 = norm.replace("\\", "/")
    if sys.platform == "win32":
        key2 = key2.lower()
    expect2 = "mailbus-" + hashlib.sha256(key2.encode("utf-8")).hexdigest()[:16] + ".lock"
    assert os.path.basename(utils._lock_path(str(tmp_path / "outside.json"))) == expect2


def test_named_lock_uses_same_root(lock_env):
    """named_lock 与 file_lock 同锁根（stale 清理命令统一扫描）。"""
    acquired = False
    from lib.infra.utils import named_lock

    with named_lock("d16-test", blocking=True, timeout=5.0) as ok:
        acquired = ok
    assert acquired
    assert os.path.exists(os.path.join(str(lock_env), "d16-test.lock"))
