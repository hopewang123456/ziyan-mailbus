---
created: 2026-08-05
updated: 2026-08-05
project: mailbus
type: design-notes
status: implemented
owner: 瀛愯█
tags: [mailbus, migration, crud, RoleDataRoot]
source: cursor-agent
local_root: E:\ai_tools\mail
---

# Agent CRUD + 璺ㄦ鏋惰縼绉?路 璁捐鎷嶆澘

> 浠ｇ爜宸插疄鐜帮紙2026-08-05锛夈€傛灦鏋勭储寮曪細[[Agent/01-mailbus/016-docs/0161-architecture/ARCHITECTURE|ARCHITECTURE 搂3.1]]銆?

## 鍒嗗眰

`api 鈫?application 鈫?ports 鈫?adapters`锛沗composition.py` 缁勮銆?

| 妯″潡 | 鑱岃矗 |
|------|------|
| `FrameworkWorkspacePort` | 甯冨眬/FileOp/MCP/绔彛/purge |
| `agent_admin` | CRUD |
| `transfer_saga` | 杩佺Щ鐘舵€佹満 |
| `transfer_rewrite` | 浠?new_id 鍘嗗彶 rewrite |
| `adapters/frameworks/workspace/*` | 鍏鏋?+ deepagent/deerflow stub |

## 宸查攣瀹氾紙鎽樿锛?

- C1=A / C7锛氭樉寮忚縼绉宦稢RUD 纭鍙啓鍘熺敓閰嶇疆锛涙棩甯稿惎鍋滀笉瑕嗙洊
- C2=B锛氭鏋?container|host 浜掓枼锛涘彧璁ゅ凡閰嶇疆鐜锛屽叾瀹冪幆澧冧笉鑷姩鎵?
- C3锛氫笉鍑?13锛涜鑹叉暟璇?mailbus 鐧昏
- C4锛氱粺涓€閰嶇疆锛屽垎鏁ｈ鍙?
- C5锛氫笉鏀规鏋舵簮鐮?
- C6锛氬悓 Agent 鍙叡浜畨瑁咃紱鍚勬湁娓呭崟锛涚嫭鍗犺矾寰?绔彛/璇激鍏变韩娈垫墠鍐茬獊
- 杩涘害/閿佽秴鏃跺洖婊氾紱鎴愬姛鍚庝笅鏋舵垨褰诲簳鍒犻櫎锛涜縼鍚?ask_start
- Docker锛歨ost_binds 绾冲叆娓呭崟

## runtime_plane 瀹℃牳琛?

| 閰嶇疆闈?| 浜掓枼瑕佺偣 |
|--------|----------|
| enabled / runtime_plane / mount_mode | 鍗曢潰鍚敤 |
| push.cwd / push.env | 鎸夐潰鍒嗗弶 |
| docker / ports / host_binds | 鎸夐潰 |
| mailbus_claude.platforms | 涓嶅弻寮€ |
| launch Win/WSL/docker | 鍗曞叆鍙?|
| 瑙掕壊 MCP / AM URL | 闅?plane profile |
| gateway/dashboard 绔彛 | 涓嶆挒杞?|
