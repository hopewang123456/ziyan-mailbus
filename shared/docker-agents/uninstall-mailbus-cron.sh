#!/bin/bash
# [DEPRECATED] 本脚本依赖旧 Python 栈的 ``python/lib/adapters/plane.post_start``，
# 已于 commit d25854e 移除。当前仓库中没有任何服务/entrypoint 调用本脚本，
# 如需重新启用，先重写其 Python 部分（改为新栈 mailbus.bootstrap.container 或等价逻辑）。
# 此脚本保留仅作历史存档，请勿在生产中执行。
set -euo pipefail
echo "uninstall-mailbus-cron.sh: 已失效 — 旧 lib 栈已移除，无等效重写。" >&2
exit 1
