#!/bin/bash
# 安装/覆盖 post-commit hook 到目标仓库的 .git/hooks/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_SOURCE="$SCRIPT_DIR/post-commit-hook.sh"

ALL_REPOS=(
    "/mnt/e/ai_tools/mail"
    "/mnt/e/hermes-data/.hermes/hermes-agent"
    "/mnt/e/hermes-data/tarot-miniapp"
    "/mnt/e/ai_tools/openclaw_space"
    "/mnt/e/ai_tools/opencode"
)

if [ ! -f "$HOOK_SOURCE" ]; then
    echo "✗ 源 hook 未找到: $HOOK_SOURCE"
    exit 1
fi

install_count=0

for repo in "${ALL_REPOS[@]}"; do
    git_dir="$repo/.git"
    hooks_dir="$git_dir/hooks"
    hook_dest="$hooks_dir/post-commit"

    if [ ! -d "$git_dir" ]; then
        echo "  ⚠ 跳过 (非 git 仓库): $repo"
        continue
    fi

    mkdir -p "$hooks_dir"
    cp "$HOOK_SOURCE" "$hook_dest"
    chmod +x "$hook_dest"
    echo "  ✓ 已安装: $hook_dest"
    install_count=$((install_count + 1))
done

echo ""
echo "✅ 完成: $install_count 个已安装"
