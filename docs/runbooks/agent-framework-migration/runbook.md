---
created: 2026-08-05
updated: 2026-08-05
project: mailbus
type: docs
status: active
owner: 瀛愯█
---

# Runbook

> 瀹炵幇瀵圭収锛歔[Agent/01-mailbus/016-docs/0161-architecture/ARCHITECTURE|ARCHITECTURE 搂3.1]]

1. 椹鹃┒鑸?鈫?妯″瀷 鈫?**Agent** 椤电锛欳RUD 鐧昏 `data_root` / docker / `runtime_plane`
2. **杩佺Щ**椤电锛氶€夎鑹层€佺洰鏍囨鏋躲€乨ry_run锛堢湅 `host_binds` / ops锛?
3. 纭瑕嗙洊/婧愬鐞嗭紙涓嬫灦|褰诲簳鍒犻櫎锛夆啋 鎵ц 鈫?杩涘害鏉¤疆璇?job
4. 澶辫触锛氳嚜鍔ㄥ洖婊氾紱`rollback_partial` 鍙己鍒跺啀杩?
5. 鎴愬姛锛氭彁绀烘槸鍚︽媺璧凤紱鏍￠獙 MCP/绔彛

| API | 鐢ㄩ€?|
|-----|------|
| `GET\|POST /api/agents/admin` | 鍒楄〃 / create\|update\|delete |
| `POST /api/agents/{id}/transfer` | `dry_run` 鎴栧惎鍔?|
| `GET\|POST /api/agents/transfer/{job_id}` | 杩涘害 / `start:true` |
| `GET /api/workspaces` | 妗嗘灦鍒楄〃 |

浠ｇ爜锛歚lib/application/agent_admin.py` 路 `transfer_saga.py` 路 `transfer_rewrite.py` 路 `adapters/frameworks/workspace/` 路 `web/src/components/LlmModelsForm.tsx`
