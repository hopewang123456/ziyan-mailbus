#!/usr/bin/env python3
"""ziyan-mailbus 测试套件入口"""

import os
import sys
import subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)


def run_test_file(name: str) -> bool:
    """运行单个测试文件，返回是否通过"""
    path = os.path.join(TESTS_DIR, name)
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    result = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    print(result.stdout)
    if result.stderr:
        print(f"  [stderr]\n{result.stderr}")
    return result.returncode == 0


def main():
    test_files = sorted(f for f in os.listdir(TESTS_DIR) if f.startswith("test_") and f.endswith(".py"))
    
    if not test_files:
        print("没有测试文件")
        return 1
    
    all_passed = True
    for f in test_files:
        if not run_test_file(f):
            all_passed = False
    
    print(f"\n{'='*50}")
    if all_passed:
        print(f"  ✓ 全部 {len(test_files)} 个测试文件通过")
        return 0
    else:
        print(f"  ✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
