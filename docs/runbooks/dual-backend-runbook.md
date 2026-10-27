# 双后端并跑 Runbook（D14）

## 端口规约
| 后端 | 端口 | 说明 |
|------|------|------|
| python serve | 9814 | 稳定实现，指标/发令/助手全能力 |
| java serve | 9815 | M1 预览；本地 mvn 跑法请用**绝对路径** `--mailbus.data-dir`（相对探测在多模块 cwd 下不稳，docker 不受影响） |
| 前端 | 随 serve 静态托管 | 同一 `web/dist` 产物，双后端各自托管 |

## Docker 并跑（推荐）
```bash
cd web && npm run build && cd ..
docker compose -f docker-compose.dual.yml up --build -d
# python: http://localhost:9814  ·  java: http://localhost:9815
```

## Java AI 助手激活（可选）
```bash
export SPRING_AI_OPENAI_BASE_URL=http://host.docker.internal:11434/v1   # ollama
export SPRING_AI_OPENAI_API_KEY=sk-any
docker compose -f docker-compose.dual.yml up -d mailbus-java
# 应用配置 mailbus.ai.enabled=true（application.yml 或 -D 参数）
```

## 已知差异（双栈）
- 指标：python 自研 query 端点 + 时序；java Micrometer `/actuator/metrics/mailbus.*`（同一 manifest 口径）
- AI 助手：两栈各自可用（同一 docs/ 知识库）
- 任务 FSM/发令后端：python 完整；java 随 M2
