"""给 hermes 0.19 的 6 个 profile 配 dashboard basic_auth。

0.19 起 dashboard 公开绑定(0.0.0.0)强制 auth provider；--insecure 已 no-op。
方案：username=ziyan + 随机密码，hash 后写入每个 profile 的 config.yaml。
密码明文存 mailbus store/secrets.json（已有 secrets 机制）。
"""
import json
import secrets
import string
import subprocess
import sys
from pathlib import Path

PROFILES = ["lingzhao", "lingxi", "lingxun", "lingjin", "lingtuo", "lingzhang"]
HERMES_DATA = Path(r"E:\ai_tools\Agent\docker\hermes-data")
SECRETS = Path(r"E:\ai_tools\mailbus\store\secrets.json")
USERNAME = "ziyan"

def gen_hash(password: str) -> str:
    # 容器内 hermes 的 hash 函数（plugins.dashboard_auth.basic.hash_password）
    out = subprocess.run(
        ["wsl", "docker", "exec", "docker-agents-hermes-1", "python3.12", "-c",
         f"from plugins.dashboard_auth.basic import hash_password; print(hash_password({password!r}))"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        sys.exit(f"hash 生成失败: {out.stderr[:300]}")
    return out.stdout.strip().splitlines()[-1]

def main():
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(16))
    digest = gen_hash(password)
    print(f"password={password}\nhash={digest[:24]}...")

    # secrets.json：备份 + 写入
    data = json.loads(SECRETS.read_text(encoding="utf-8"))
    SECRETS.with_suffix(".json.bak-dash-auth").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    data["hermes_dashboard_basic_auth"] = {"username": USERNAME, "password": password}
    SECRETS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    block = (
        "\n# mailbus: hermes 0.19 dashboard 公开绑定强制 auth（--insecure 已 no-op）\n"
        "dashboard:\n"
        "  basic_auth:\n"
        f"    username: {USERNAME}\n"
        f"    password_hash: {digest}\n"
    )
    for p in PROFILES:
        cfg = HERMES_DATA / "profiles" / p / "config.yaml"
        text = cfg.read_text(encoding="utf-8", errors="replace")
        if "basic_auth" in text:
            print(f"{p}: 已有 basic_auth，跳过")
            continue
        cfg.with_suffix(".yaml.bak-dash-auth").write_text(text, encoding="utf-8")
        cfg.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
        print(f"{p}: ok")

if __name__ == "__main__":
    main()
