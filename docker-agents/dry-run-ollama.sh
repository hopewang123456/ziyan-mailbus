#!/bin/bash
TASK_ID="verify-ollama-$(date +%s)"
curl -s -X POST http://127.0.0.1:9814/api/internal-llm/dry-run \
  -H 'Content-Type: application/json' \
  -d "{\"intent\":\"评估 Redis 缓存方案\",\"task_type\":\"custom\",\"tier\":\"M\",\"task_id\":\"${TASK_ID}\"}" \
  | python3 -m json.tool
