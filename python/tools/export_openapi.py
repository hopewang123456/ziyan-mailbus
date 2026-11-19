"""导出新栈 OpenAPI 到 shared/contracts/generated/openapi.json。

用法：
    python tools/export_openapi.py          # 重新导出
    python tools/export_openapi.py --check  # 只校验是否漂移
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "shared" / "contracts" / "generated" / "openapi.json"

sys.path.insert(0, str(REPO_ROOT / "python"))


def main() -> int:
    from mailbus.bootstrap.main import create_app

    spec = create_app().openapi()
    text = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"契约已漂移：{TARGET}")
            return 1
        print("契约一致")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"已导出：{TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
