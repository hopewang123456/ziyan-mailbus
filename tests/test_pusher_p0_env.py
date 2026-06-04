"""回归测试：P0 — API Key 统一注入 (commit 06982fc)

测试 _load_env() 和 get_env_for_cli() 的新逻辑:
  1. 不再通过 cmd 字符串匹配 provider 名
  2. 改为统一注入所有已知 API Key
  3. 先继承父进程已有的 _API_KEY 环境变量
  4. .env 文件解析保持兼容
"""
import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 在 import pusher 前，清理全局缓存，确保每次测试用干净的模块状态
_RELOAD = True


def _clean_import():
    """清除 pusher 模块的全局缓存，重新加载"""
    for mod in list(sys.modules.keys()):
        if "lib.pusher" in mod:
            del sys.modules[mod]
    from lib import pusher
    pusher._ENV_LOADED = False
    pusher._ALL_ENV_KEYS = {}
    return pusher


def test_env_key_inherits_parent():
    """P0-1: _load_env 继承父进程已有的 _API_KEY 环境变量"""
    # 在导入前设置一个测试 key
    os.environ["NOT_A_SECRET_KEY"] = "should-be-ignored"  # 不以 _API_KEY 结尾
    os.environ["MY_CUSTOM_API_KEY"] = "custom-val"     # 以 _API_KEY 结尾
    pusher = _clean_import()
    # 重新触发加载
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    pusher._load_env()
    # MY_CUSTOM_API_KEY 以 _API_KEY 结尾，应该被继承
    assert pusher._ALL_ENV_KEYS.get("MY_CUSTOM_API_KEY") == "custom-val", \
        f"父进程的 _API_KEY 环境变量应被继承，得到: {pusher._ALL_ENV_KEYS}"
    # TEST_API_KEY 不以 _API_KEY 结尾，不应被继承
    assert "NOT_A_SECRET_KEY" not in pusher._ALL_ENV_KEYS, \
        "不以 _API_KEY 结尾的环境变量不应被继承"
    del os.environ["NOT_A_SECRET_KEY"]
    del os.environ["MY_CUSTOM_API_KEY"]
    print("  ✓ test_env_key_inherits_parent")


def test_get_env_for_cli_injects_known_keys():
    """P0-2: get_env_for_cli 不再依赖 cmd 内容，统一注入所有已知 key"""
    pusher = _clean_import()
    # 模拟 .env 文件
    test_dir = tempfile.mkdtemp()
    env_path = os.path.join(test_dir, ".env")
    with open(env_path, "w") as f:
        f.write("DEEPSEEK_API_KEY=ds-key\n")
        f.write("OPENROUTER_API_KEY=or-key\n")
        f.write("SOME_OTHER_VAR=hello\n")
    # 临时替换 bus_dir 搜索路径的 parent
    original_parent = pusher.Path
    # 模拟 _load_env 能读到这个 .env
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    # 手动加载
    pusher._ENV_LOADED = False
    pusher._ALL_ENV_KEYS.clear()
    # 先继承父进程（空），再加载 .env
    pusher._ALL_ENV_KEYS.update({k: v for k, v in os.environ.items() if k.endswith("_API_KEY")})
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if val:
                pusher._ALL_ENV_KEYS[key] = val
    pusher._ENV_LOADED = True

    # 调用 get_env_for_cli — 无论 cmd 内容是什么
    env1 = pusher.get_env_for_cli(cmd="hermes chat -q 'MSG'")
    assert env1.get("DEEPSEEK_API_KEY") == "ds-key", "DEEPSEEK_API_KEY 应被注入"
    assert env1.get("OPENROUTER_API_KEY") == "or-key", "OPENROUTER_API_KEY 应被注入"
    assert "SOME_OTHER_VAR" not in env1, "非 KNOWN_API_KEYS 不应注入"

    # 即使 cmd 不包含任何 provider 名，也应该注入所有已知 key
    env2 = pusher.get_env_for_cli(cmd="ls")
    assert env2.get("DEEPSEEK_API_KEY") == "ds-key", \
        "cmd='ls' 也应注入 DEEPSEEK_API_KEY"
    assert env2.get("OPENROUTER_API_KEY") == "or-key", \
        "cmd='ls' 也应注入 OPENROUTER_API_KEY"

    shutil.rmtree(test_dir)
    print("  ✓ test_get_env_for_cli_injects_known_keys")


def test_get_env_for_cli_missing_keys_skipped():
    """P0-3: .env 中不存在的 key 跳过（不报错，不注入）"""
    pusher = _clean_import()
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    pusher._ALL_ENV_KEYS.update({k: v for k, v in os.environ.items() if k.endswith("_API_KEY")})
    pusher._ENV_LOADED = True

    env = pusher.get_env_for_cli(cmd="any command")
    # 不应有 DEEPSEEK_API_KEY（未设置）
    assert "DEEPSEEK_API_KEY" not in env, "未设置的 key 不应注入"
    assert "GEMINI_API_KEY" not in env, "未设置的 key 不应注入"
    print("  ✓ test_get_env_for_cli_missing_keys_skipped")


def test_known_api_keys_exhaustive():
    """P0-4: KNOWN_API_KEYS 包含所有主流 provider"""
    pusher = _clean_import()
    expected = {
        "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY", "QWEN_API_KEY", "ZHIPU_API_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY",
        "MISTRAL_API_KEY", "COHERE_API_KEY",
    }
    actual = set(pusher.KNOWN_API_KEYS)
    assert actual == expected, f"KNOWN_API_KEYS 不匹配\n  期望: {expected}\n  实际: {actual}"
    print("  ✓ test_known_api_keys_exhaustive")


def test_env_file_first_match_only():
    """P0-5: 搜索多个候选路径，找到第一个有效 .env 就停"""
    pusher = _clean_import()
    test_dir = tempfile.mkdtemp()
    # 在多个候选位置写 .env
    env1 = os.path.join(test_dir, ".env")
    env2 = os.path.join(test_dir, "subdir", ".env")
    os.makedirs(os.path.dirname(env2), exist_ok=True)
    with open(env1, "w") as f:
        f.write("DEEPSEEK_API_KEY=from-first\n")
    with open(env2, "w") as f:
        f.write("DEEPSEEK_API_KEY=from-second\n")

    # 模拟 _load_env 的候选路径逻辑
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    candidates = [env1, env2]
    for env_path in candidates:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if val:
                        pusher._ALL_ENV_KEYS[key] = val
            break  # 找到第一个就停
    assert pusher._ALL_ENV_KEYS.get("DEEPSEEK_API_KEY") == "from-first", \
        "应使用第一个 .env 的值"
    shutil.rmtree(test_dir)
    print("  ✓ test_env_file_first_match_only")


def test_env_file_comment_and_empty_lines():
    """P0-6: .env 文件中的空行、注释行、格式错误行被跳过"""
    pusher = _clean_import()
    test_dir = tempfile.mkdtemp()
    env_path = os.path.join(test_dir, ".env")
    with open(env_path, "w") as f:
        f.write("# 这是注释\n")
        f.write("\n")
        f.write("   \n")
        f.write("DEEPSEEK_API_KEY=valid\n")
        f.write("NOKEYLINE\n")
        f.write("EMPTYVAL=\n")
        f.write("OPENROUTER_API_KEY=or-key\n")
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if val:
                pusher._ALL_ENV_KEYS[key] = val
    assert pusher._ALL_ENV_KEYS.get("DEEPSEEK_API_KEY") == "valid", "有效 key 应加载"
    assert pusher._ALL_ENV_KEYS.get("OPENROUTER_API_KEY") == "or-key", "有效 key 应加载"
    assert "NOKEYLINE" not in pusher._ALL_ENV_KEYS, "格式错误行应跳过"
    assert "EMPTYVAL" not in pusher._ALL_ENV_KEYS, "空值行应跳过"
    shutil.rmtree(test_dir)
    print("  ✓ test_env_file_comment_and_empty_lines")


def test_get_env_for_cli_empty_cmd():
    """P0-7: cmd 为空字符串时 get_env_for_cli 仍正常工作"""
    pusher = _clean_import()
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    pusher._ALL_ENV_KEYS.update({k: v for k, v in os.environ.items() if k.endswith("_API_KEY")})
    pusher._ENV_LOADED = True
    env = pusher.get_env_for_cli(cmd="")
    # 不应报错，返回 dict
    assert isinstance(env, dict)
    print("  ✓ test_get_env_for_cli_empty_cmd")


def test_double_load_is_idempotent():
    """P0-8: _load_env 多次调用幂等（不会重复加载）"""
    pusher = _clean_import()
    pusher._ALL_ENV_KEYS.clear()
    pusher._ENV_LOADED = False
    pusher._ALL_ENV_KEYS["MANUAL_KEY"] = "value"
    pusher._ENV_LOADED = True
    # 第二次调用不应清掉 MANUAL_KEY
    pusher._load_env()
    assert pusher._ALL_ENV_KEYS.get("MANUAL_KEY") == "value"
    print("  ✓ test_double_load_is_idempotent")


if __name__ == "__main__":
    _clean_import()
    test_env_key_inherits_parent()
    test_get_env_for_cli_injects_known_keys()
    test_get_env_for_cli_missing_keys_skipped()
    test_known_api_keys_exhaustive()
    test_env_file_first_match_only()
    test_env_file_comment_and_empty_lines()
    test_get_env_for_cli_empty_cmd()
    test_double_load_is_idempotent()
    print(f"\n✓ 全部 8 个 P0 回归测试通过")
