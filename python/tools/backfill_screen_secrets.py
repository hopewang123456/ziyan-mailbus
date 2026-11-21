"""回填大屏密钥（M14）。

推荐：通过管理员登记接口回填并保留原密钥
    python tools/backfill_screen_secrets.py --via-api --token <管理员Token> \
        --base-url http://127.0.0.1:9814 --out data/screen-secrets.json

    ``POST /api/collab/screens`` 对已存在的大屏保留原密钥并原样回显，因此重复执行
    不会重置密钥；结果写入 ``--out``（默认 ``<data_dir>/screen-secrets.json``）。
    注意：登记会把 ``online`` 置为 True，执行后 60 秒内大屏列表显示为在线，
    随后按 TTL 自动回落，无需额外处理。

备用：直连数据库（后端停机时使用，幂等，仅补 NULL 密钥）
    python tools/backfill_screen_secrets.py [--data-dir D] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

_PENDING_SQL = (
    "SELECT screen_id, name FROM collab_screens"
    " WHERE secret IS NULL OR secret = ''"
    " ORDER BY created_at, screen_id"
)


def _new_secret() -> str:
    return secrets.token_urlsafe(24)


def _request(
    base_url: str, token: str, method: str, path: str, payload: dict | None = None
) -> tuple[int, object]:
    url = base_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _fill_via_api(
    base_url: str, token: str, out_path: Path | None, dry_run: bool
) -> int:
    status, screens = _request(base_url, token, "GET", "/api/collab/screens")
    if status != 200 or not isinstance(screens, list):
        print(f"读取大屏列表失败：HTTP {status} {screens}")
        return 1
    if dry_run:
        print(f"待处理 {len(screens)} 个大屏（dry-run，未调用登记）：")
        for screen in screens:
            print(f"  - {screen['screen_id']}\t{screen['name']}")
        return 0

    entries: list[dict[str, object]] = []
    for screen in screens:
        screen_id = screen["screen_id"]
        code, created = _request(
            base_url,
            token,
            "POST",
            "/api/collab/screens",
            {
                "screen_id": screen_id,
                "name": screen["name"],
                "floor_id": screen.get("floor_id"),
                "seat_id": screen.get("seat_id"),
            },
        )
        if code != 201 or not isinstance(created, dict):
            print(f"登记失败 {screen_id}：HTTP {code} {created}")
            return 1
        entries.append(
            {
                "screen_id": screen_id,
                "name": screen["name"],
                "secret": created.get("secret"),
            }
        )

    if out_path is None:
        for entry in entries:
            print(f"  {entry['screen_id']}\t{entry['name']}\t{entry['secret']}")
        print(f"已通过管理员登记接口保留 {len(entries)} 个大屏密钥")
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"base_url": base_url, "screens": entries}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"已通过管理员登记接口保留 {len(entries)} 个大屏密钥：{out_path}")
    return 0


def _fill_via_db(data_dir: Path | None, dry_run: bool) -> int:
    from mailbus.adapters.persistence.sqlite.connection import connect
    from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
    from mailbus.bootstrap.settings import Settings

    settings = Settings(data_dir=data_dir) if data_dir else Settings.from_env()
    db_path = settings.db_path
    if not db_path.exists():
        print(f"数据库不存在：{db_path}")
        return 1

    conn = connect(db_path)
    try:
        apply_migrations(conn)  # 确保 secret 列（014）存在
        pending = conn.execute(_PENDING_SQL).fetchall()
        if not pending:
            print("无需回填：所有大屏均已配置密钥")
            return 0
        if dry_run:
            print(f"待回填 {len(pending)} 个大屏：")
            for row in pending:
                print(f"  - {row['screen_id']}\t{row['name']}")
            return 0

        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in pending:
                conn.execute(
                    "UPDATE collab_screens SET secret = ?"
                    " WHERE screen_id = ? AND (secret IS NULL OR secret = '')",
                    (_new_secret(), row["screen_id"]),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        ids = [row["screen_id"] for row in pending]
        marks = ",".join("?" * len(ids))
        updated = conn.execute(
            f"SELECT screen_id, name, secret FROM collab_screens"
            f" WHERE screen_id IN ({marks}) ORDER BY created_at, screen_id",
            ids,
        ).fetchall()
        print(f"已回填 {len(updated)} 个大屏：")
        for row in updated:
            print(f"  {row['screen_id']}\t{row['name']}\t{row['secret']}")
        print("\n密钥已立即生效：大屏心跳/离线须携带 secret；页面刷新会自动重新登记。")
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回填大屏密钥（M14）")
    parser.add_argument("--via-api", action="store_true", help="走管理员登记接口")
    parser.add_argument("--token", default=os.environ.get("MAILBUS_ADMIN_TOKEN"))
    parser.add_argument("--base-url", default="http://127.0.0.1:9814")
    parser.add_argument("--out", type=Path, default=None, help="密钥导出路径")
    parser.add_argument("--data-dir", type=Path, default=None, help="数据目录")
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理项")
    args = parser.parse_args(argv)

    if not args.via_api:
        return _fill_via_db(args.data_dir, args.dry_run)

    if not args.token:
        print("缺少管理员 Token：请传 --token 或设置 MAILBUS_ADMIN_TOKEN")
        return 2
    out_path = args.out
    if out_path is None:
        from mailbus.bootstrap.settings import Settings

        settings = Settings(data_dir=args.data_dir) if args.data_dir else Settings.from_env()
        out_path = settings.data_dir / "screen-secrets.json"
    return _fill_via_api(args.base_url, args.token, out_path, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
