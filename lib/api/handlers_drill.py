"""video_publish 演练 API。"""

from __future__ import annotations

from lib.drill.video_publish import run_video_publish_drill


def handle_drill_video_publish(handler):
    body = handler._read_post_body()
    mode = (body.get("mode") or "dry").lower()
    live = bool(body.get("live"))
    result = run_video_publish_drill(handler.data_dir, mode=mode, live=live)
    # 演练结果始终 200，由 ok 字段表示成败（便于 Dashboard 展示 steps）
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result})
