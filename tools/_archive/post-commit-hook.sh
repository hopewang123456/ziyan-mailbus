#!/bin/bash
# post-commit hook — commit/merge 后自动审查
#   1) 跑 pytest 与 baseline 对比
#   2) 调 bus.py review 审核本次 diff
#   3) 输出报告到 store/reports/
#   4) 测试失败时自动回退（仅单 parent、未 push 的 commit）
set -euo pipefail

MAIL_HOME="$(cd "$(dirname "$0")" && pwd)"
STORE_DIR="$MAIL_HOME/store"
REPORTS_DIR="$STORE_DIR/reports"
REPO_NAME="${1:-mailbus}"
CURRENT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo "unknown")"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
REPORT_FILE="$REPORTS_DIR/review-$TIMESTAMP-$REPO_NAME.md"

mkdir -p "$REPORTS_DIR"

# ── 1. pytest 基线对比 ──
# 统一 stash 未提交改动以免干扰测试
STASH_REF=""
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    STASH_REF="$(git stash create "post-commit-hook-stash" 2>/dev/null)"
    if [ -n "$STASH_REF" ]; then
        git stash store "$STASH_REF" --message "post-commit-hook-stash" 2>/dev/null || true
    fi
fi

TEST_EXIT=0
TEST_LOG="$REPORTS_DIR/pytest-$TIMESTAMP-$REPO_NAME.log"
if command -v python3 &>/dev/null && python3 -m pytest --version &>/dev/null 2>&1; then
    python3 -m pytest "$MAIL_HOME/tests" --tb=short -q > "$TEST_LOG" 2>&1 || TEST_EXIT=$?
else
    echo "  ⚠ pytest 不可用，跳过测试" | tee -a "$TEST_LOG"
fi

# 恢复 stash
stash_pop_safe() {
    if [ -n "$STASH_REF" ]; then
        git stash pop 2>/dev/null || git stash drop 2>/dev/null || true
    fi
}
stash_pop_safe

# ── 2. bus.py review 审核 diff ──
BUS_REVIEW_EXIT=0
BUS_REVIEW_OUT="$REPORTS_DIR/bus-review-$TIMESTAMP-$REPO_NAME.log"
if [ -f "$MAIL_HOME/bus.py" ]; then
    python3 "$MAIL_HOME/bus.py" review \
        --workdir "$MAIL_HOME" \
        --data-dir "$STORE_DIR" \
        --commit HEAD \
        --semgrep \
        --output "$REPORT_FILE" \
        > "$BUS_REVIEW_OUT" 2>&1 || BUS_REVIEW_EXIT=$?
else
    echo "  ⚠ bus.py 未找到，跳过审查" | tee -a "$BUS_REVIEW_OUT"
fi

# ── 3. 测试失败 → 自动回退（仅单 parent 且未 push 的 commit）──
if [ "$TEST_EXIT" -ne 0 ]; then
    echo "⚠ pytest 失败 (exit=$TEST_EXIT)，执行回退" >> "$REPORT_FILE"

    # 检查是否 merge commit（多 parent）：只回退单 parent commit
    PARENT_COUNT=$(git rev-list --parents -n 1 HEAD 2>/dev/null | awk '{print NF-1}' | tr -d ' ')
    if [ "$PARENT_COUNT" -ne 1 ]; then
        echo "⏭ merge commit (parent=$PARENT_COUNT)，跳过自动回退" >> "$REPORT_FILE"
        exit 0
    fi

    # 检查是否已 push：有 upstream remote 则不回退
    if git rev-parse HEAD@{upstream} &>/dev/null; then
        echo "⏭ commit 已推送到远程，跳过自动回退" >> "$REPORT_FILE"
        exit 0
    fi

    # soft reset 回退最后一个 commit
    git reset --soft HEAD~1 2>/dev/null || true
    echo "⛔ 自动回退: git reset --soft HEAD~1 (测试失败)" >> "$REPORT_FILE"
fi

exit 0
