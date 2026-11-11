"""D16 批1：python ↔ java 跨进程锁互斥对打验收。

用法（仓库根）：
    python tools/d16_lock_interop.py

前置：java/mailbus-infra 已编译（target/classes 存在，mvn -pl mailbus-infra compile）。
验证：
  1. 双栈对同一 inbox.json 命中**同一个**锁文件（hash 契约，锁目录只应有一个文件）；
  2. python 进程、java 进程与父进程三方并发读改写计数精确（OS record lock 真互斥）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_LIB = os.path.join(REPO, "python")
INFRA_CLASSES = os.path.join(REPO, "java", "mailbus-infra", "target", "classes")

# 子进程脚本：MAILBUS_DATA 决定 _store_relative_key 的基准目录（双栈 hash 契约前提），
# MAILBUS_LOCK_DIR 决定锁根——两者都必须在 import lib 之前设好。
PY_CHILD = textwrap.dedent(
    """
    import sys, os
    target, py_lib, data_dir, lock_dir, n = (
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
    sys.path.insert(0, py_lib)
    os.environ["MAILBUS_DATA"] = data_dir
    os.environ["MAILBUS_LOCK_DIR"] = lock_dir
    from lib.infra.utils import file_lock, json_read, json_write
    for _ in range(n):
        with file_lock(path=target):
            cur = json_read(target, default={"a": 0}, ttl=0)
            cur["a"] = cur.get("a", 0) + 1
            json_write(target, cur)
    """
)

JAVA_CHILD = r'''
package io.github.hopewang123456.mailbus.infra.lock;

/** D16 批1 跨语言对打子进程（python tools/d16_lock_interop.py 启动）。 */
public final class InteropBumpChild {
    public static void main(String[] args) throws Exception {
        java.nio.file.Path target = java.nio.file.Path.of(args[0]);
        java.nio.file.Path dataDir = java.nio.file.Path.of(args[1]);
        int n = Integer.parseInt(args[2]);
        for (int i = 0; i < n; i++) {
            CrossProcessFileLock.withLock(target, dataDir, () -> {
                try {
                    String s = java.nio.file.Files.readString(target).replaceAll("[^0-9]", "");
                    int cur = s.isEmpty() ? 0 : Integer.parseInt(s);
                    java.nio.file.Files.writeString(target, "{\"a\": " + (cur + 1) + "}");
                } catch (Exception e) {
                    System.exit(2);
                }
            });
        }
    }
}
'''

JAVA_CHILD_CLASS = "io.github.hopewang123456.mailbus.infra.lock.InteropBumpChild"


def _jdk(name: str) -> str:
    """优先 JDK25（java 仓构建用 25；PATH 默认 17 读不了 25 的 classes）。"""
    env_jdk = os.environ.get("MAILBUS_JDK25_HOME")
    for base in (env_jdk, r"D:\jdk-25.0.4.1+1"):
        if base and os.path.isfile(os.path.join(base, "bin", name + (".exe" if os.name == "nt" else ""))):
            return os.path.join(base, "bin", name)
    return name


def _compile_java_child(tmp: str) -> str:
    """落盘 java 子进程类并编译到临时目录，返回完整 classpath。"""
    src = os.path.join(tmp, "InteropBumpChild.java")
    out_dir = os.path.join(tmp, "jcls")
    with open(src, "w", encoding="utf-8") as f:
        f.write(JAVA_CHILD)
    subprocess.run(
        [_jdk("javac"), "-cp", INFRA_CLASSES, "-d", out_dir, src],
        check=True, capture_output=True,
    )
    return os.pathsep.join([INFRA_CLASSES, out_dir])


def main() -> int:
    if not os.path.isdir(INFRA_CLASSES):
        print("FAIL: 先编译 java/mailbus-infra（mvn -pl mailbus-infra compile）")
        return 1
    tmp = tempfile.mkdtemp(prefix="d16-interop-")
    data_dir = os.path.join(tmp, "store")
    lock_dir = os.path.join(data_dir, ".locks")
    os.makedirs(os.path.join(data_dir, "inbox", "a"), exist_ok=True)
    target = os.path.join(data_dir, "inbox", "a", "inbox.json")

    # 父进程也参与对打：基准 data_dir / 锁根与两个子进程一致
    os.environ["MAILBUS_DATA"] = data_dir
    os.environ["MAILBUS_LOCK_DIR"] = lock_dir
    sys.path.insert(0, PY_LIB)
    from lib.infra.utils import file_lock, json_read, json_write

    json_write(target, {"a": 0})

    py_child = os.path.join(tmp, "py_bump.py")
    with open(py_child, "w", encoding="utf-8") as f:
        f.write(PY_CHILD)
    cp = _compile_java_child(tmp)

    n_py, n_java, n_parent = 150, 150, 50
    env = dict(os.environ)
    jv = subprocess.Popen(
        [_jdk("java"), "-cp", cp, JAVA_CHILD_CLASS, target, data_dir, str(n_java)],
        env=env,
    )
    pv = subprocess.Popen(
        [sys.executable, py_child, target, PY_LIB, data_dir, lock_dir, str(n_py)],
        env=env,
    )
    for _ in range(n_parent):
        with file_lock(path=target):
            cur = json_read(target, default={"a": 0}, ttl=0)
            cur["a"] = cur.get("a", 0) + 1
            json_write(target, cur)

    rc_j, rc_p = jv.wait(120), pv.wait(120)
    final = json_read(target, ttl=0)["a"]
    expect = n_py + n_java + n_parent

    locks = sorted(os.listdir(lock_dir))
    print(f"final={final} expect={expect} lock_files={locks}")
    ok = final == expect and rc_j == 0 and rc_p == 0 and len(locks) == 1
    print("CROSS-LANGUAGE LOCK INTEROP:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
