#!/bin/bash
# codexapp 以 root 运行时读 /root/.codex，与 CODEX_HOME=/home/node/.codex 不一致时镜像配置
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
PROJECT_DIR="${CODEX_PROJECT_DIR:-}"

mirror_roots=(/root/.codex)
if [ -n "${HOME:-}" ] && [ "${HOME}/.codex" != "$CODEX_HOME" ]; then
  mirror_roots+=("${HOME}/.codex")
fi

for dest in "${mirror_roots[@]}"; do
  [ "$dest" = "$CODEX_HOME" ] && continue
  mkdir -p "$dest"
  for f in config.toml deepseek-model-catalog.json webui-custom-providers.json .codex-global-state.json; do
    if [ -f "${CODEX_HOME}/${f}" ]; then
      cp "${CODEX_HOME}/${f}" "${dest}/${f}"
    fi
  done
  if [ -d "${CODEX_HOME}/skills" ] && [ ! -e "${dest}/skills" ]; then
    ln -sfn "${CODEX_HOME}/skills" "${dest}/skills"
  fi
done

if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR/.codex" ]; then
  cp "${CODEX_HOME}/config.toml" "${PROJECT_DIR}/.codex/config.toml" 2>/dev/null || true
  cp "${CODEX_HOME}/webui-custom-providers.json" "${PROJECT_DIR}/.codex/webui-custom-providers.json" 2>/dev/null || true
  cp "${CODEX_HOME}/deepseek-model-catalog.json" "${PROJECT_DIR}/.codex/deepseek-model-catalog.json" 2>/dev/null || true
fi
