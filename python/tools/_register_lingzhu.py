"""注册 zcode 平台 + 灵枢(lingzhu) agent 实例进 store/config.json。

不动 stations.candidates（pin 指派才接活）。备份：config.json.bak-zcode-add。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # repo root

from lib.infra.utils import json_write  # noqa: E402

CONFIG = os.path.join("store", "config.json")

with open(CONFIG, encoding="utf-8") as f:
    cfg = json.load(f)

assert "lingzhu" not in cfg.get("agents", {}), "lingzhu 已存在"
assert "zcode" not in cfg.get("agent_types", {}), "agent_types.zcode 已存在"

# 1) agent_types.zcode：push 模板（adapter 存在时不走此模板，留作 fallback/文档）
cfg["agent_types"]["zcode"] = {
    "push": "zcode -p 'MSG' --mode yolo",
    "description": "ZCode CLI（宿主 headless · GLM 后端 · Z.AI OAuth）",
}

# 2) models 映射：glm 别名对 zcode 无 flag（GLM 内置后端）
cfg["agent_types"].setdefault("models", {}).setdefault("glm", {})

# 3) agents.lingzhu
cfg["agents"]["lingzhu"] = {
    "name": "灵枢",
    "role": "通用工程",
    "type": "zcode",
    "agent_id": "lingzhu",
    "archetype": "coding-executor",
    "max_concurrency": 1,
    "models": ["glm"],
    "inbox": "E:/ai_tools/mailbus/store/inbox/lingzhu/inbox.json",
    "push": {"cwd": "E:\\ai_tools\\Agent\\zcode\\workspaces\\lingzhu"},
    "launch": {
        "template": "zcode_cli",
        "has_browser": False,
        "launch_via_api": False,
        "cli": {"kind": "shell", "start_wait_seconds": 0},
    },
    "profile_paths": {"identity": "01-mailbus/018-identities/lingzhu/overlay.md"},
    "push_timeout_seconds": 600,
    "available": True,
    "enabled": True,
    "auth": {"mode": "none", "note": "headless CLI，无浏览器入口"},
    "zcode": {"mode": "yolo"},
    "run_target": "windows",
}

json_write(CONFIG, cfg, indent=1)
print("config.json 已写入：agent_types.zcode + agents.lingzhu")

# inbox 目录 + 首条系统消息（镜像 init_store/agent-add 模式）
inbox_dir = os.path.join("store", "inbox", "lingzhu")
os.makedirs(inbox_dir, exist_ok=True)
inbox_path = os.path.join(inbox_dir, "inbox.json")
if not os.path.exists(inbox_path):
    welcome = [{
        "id": "sys-lingzhu-0001",
        "to": "lingzhu",
        "from": "mailbus",
        "priority": "normal",
        "type": "system",
        "content": "你已加入 mailbus 总线，编制名 灵枢（lingzhu）。收到 task 类消息时：读内容、执行、按 reply_format 把结果写到指定 msg-results 路径并 ack。",
        "state": "read",
    }]
    json_write(inbox_path, welcome, indent=1)
    print("inbox 已初始化:", inbox_path)

# 工作区 + per-agent ZCODE_HOME
for d in (
    r"E:\ai_tools\Agent\zcode\workspaces\lingzhu",
    r"E:\ai_tools\Agent\zcode\homes\.zcode-lingzhu",
):
    os.makedirs(d, exist_ok=True)
    print("dir ok:", d)
