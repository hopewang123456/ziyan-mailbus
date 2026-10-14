#!/usr/bin/env bash
set -euo pipefail
docker exec docker-agents-hermes-1 sh -c 'env | grep -iE "HERMES_DASHBOARD|SESSION|TOKEN" | head -30 || true'
echo '---'
docker exec docker-agents-hermes-1 sh -c 'ps aux | grep -i dashboard | grep -v grep | head -10 || true'
