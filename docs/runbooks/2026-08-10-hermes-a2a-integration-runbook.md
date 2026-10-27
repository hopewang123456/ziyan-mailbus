---
created: 2026-08-10
project: mailbus
project_path: Agent/docs/mailbus
type: runbook
status: active
owner: 瀛愯█
tags: [mailbus, hermes, a2a, docker, upgrade]
source: cursor-agent
local_root: E:\ai_tools\mail
---

# Hermes v0.20.0 鍗囩骇 + A2A 闆嗘垚 mailbus 瀹屾垚鎶ュ憡

## TL;DR

- hermes 瀹瑰櫒闀滃儚閲嶅缓涓?**v0.20.0**锛堝惈 A2A 鎻掍欢锛孭yPI 鏃犳鐗堟湰锛屾敼浠庢簮鐮?editable 瀹夎锛夈€?
- hermes A2A inbound 绔偣鍦ㄥ鍣ㄥ唴 **`hermes:9900`** 鎸佷箙杩愯锛堝凡鎵樼杩?entrypoint锛夈€?
- mailbus 6 涓?hermes_profile agents锛坙ingzhao/lingjin/lingxi/lingxun/lingtuo/lingzhang锛夊凡閰?A2A 閫氶亾锛?*Router 浼樺厛璧?A2A锛? 娆″け璐ヨ嚜鍔ㄩ檷绾?file_bus**銆?
- 淇 mailbus A2A 瀹㈡埛绔竴涓湡瀹炲吋瀹规€?bug锛欰2A 鏍囧噯 `Task.status` 鏄?`TaskStatus` 瀵硅薄锛屾棫浠ｇ爜璇綋瀛楃涓层€?
- 绔埌绔疄娴嬶細mailbus 鈫?hermes:9900 A2A 涓€娆℃垚鍔燂紙PONG锛夛紝闄嶇骇璺緞涔熷疄娴嬮€氳繃銆?
- **琛ュ厖锛堝悓浼氳瘽锛?*锛?
  - docker 鍐呭叾浣?agent 鍗囩骇鍒版渶鏂帮細codex 0.142.0鈫?*0.147.0**锛坓ateway 0.1.5鈫?*0.2.5**锛夈€乷pencode 1.17.9鈫?*1.18.15**锛坥penclaw 2026.7.1-2 宸叉渶鏂帮級锛涗慨澶?2 涓?skills 鍚屾鑴氭湰 CRLF銆?
  - A2A 鍑虹珯璋冪敤妯″紡鐢?*璁捐妯″紡**閲嶆瀯锛堢瓥鐣?+ 妯℃澘鏂规硶 + 闂ㄩ潰锛夛紝涓嶅啀鍫嗗湪涓€涓柟娉曢噷銆?
  - **浜屾纭椤瑰叏閮ㄥ鐞?*锛歵tyd 杩?git锛圓1-a锛夈€佸菇鐏靛悓姝ヨ剼鏈垹闄わ紙A2锛夈€丄2A slug 鍐峰惎鍔ㄥ蹇嶏紙A3-a锛宲oll/瓒呮椂閰嶇疆锛夈€乄SL 鍐呭瓨鍥哄畾锛圕6-a锛宍memory=12GB` 宸茬敓鏁堬級銆乧ompose sync 鐢熸垚婧愬姞 A2A env + 淇洏绗?bug锛圕7-a锛夈€乵ailbus 闀滃儚鍥哄寲 pytest锛圕8锛夈€傞『甯︿慨 agentmemory NODE_MODULES 璺緞 bug銆乭ermes entrypoint 鑷姩鎷?gateway锛堣瑙併€屼笁路琛ヤ笁銆嶏級銆?

## 鑳屾櫙

鐢ㄦ埛閫夋嫨銆岃矾寰?B銆嶏細閲嶅缓 hermes 瀹瑰櫒闀滃儚鍒?v0.20.0 骞跺惎鐢?A2A锛岃 mailbus 鐩磋繛 hermes A2A 绔偣銆?

## 涓€銆丠ermes 瀹瑰櫒鍗囩骇

### 1. 闀滃儚閲嶅缓锛坴0.17.0 鈫?v0.20.0锛?

- **鍗＄偣**锛歅yPI 鏈€鏂颁粎 0.19.0锛屼笖 hermes `setup.py` 鏄庣‘绂佹鏋勫缓 wheel 鈫?鍙兘浠庢簮鐮?editable 瀹夎銆?
- **鍋氭硶**锛?
  - `git archive` 鎵撳寘瀹夸富 v0.20.0 婧愮爜锛坱ag `v2026.8.3`锛夆啋 `hermes-base/hermes-src.tar.gz`锛?1M锛夈€?
  - `hermes-base/Dockerfile` 鏀逛负浼樺厛浠庢湰鍦?tar 婧愮爜 `pip install -e`锛屾簮鐮佷繚鐣欏湪 `/opt/hermes/hermes-agent`銆?
  - 浠庤繍琛屽鍣ㄥ鍒剁己澶辩殑 `sync-identities.sh` 杩?build context銆?
- **浜х墿**锛氶暅鍍?`docker-agents-hermes:latest` 鍐?hermes v0.20.0 + A2A 鎻掍欢灏变綅銆?

### 2. 棣栨鍚姩鍗′綇鏍瑰洜涓庝慨澶?

- **鐥囩姸**锛歚hermes gateway run` 鍚姩鏃╂湡鍗抽樆濉烇紙鐘舵€?`D`锛宍wchan=p9_client_rpc`锛夈€?
- **鏍瑰洜**锛歚cmd_gateway 鈫?_sync_bundled_skills_quietly 鈫?sync_skills` 閫掑綊鎵弿 skills 鐩綍锛坄rglob("SKILL.md")`锛夛紝璇ョ洰褰?symlink 鎸囧悜 Vault 鎶€鑳藉簱锛屾寕鍦?9p/NTFS 鎱?IO 涓娿€?
- **淇**锛氬湪 `HERMES_HOME` 鍒涘缓瀹樻柟 opt-out marker **`.no-bundled-skills`**锛宍sync_skills` 绔嬪嵆杩斿洖銆?

### 3. Dashboard Auth Gate锛坴0.20.0 鏂板姞鍥猴級

- **鐥囩姸**锛氬鍣ㄥ弽澶嶉噸鍚紝dashboard 鎷掔粷缁戝畾 `0.0.0.0`銆?
- **鏍瑰洜**锛歷0.20.0 璧烽潪 loopback 缁戝畾**蹇呴』**鏈?auth provider锛宍--insecure` 涓嶅啀缁曡繃銆?
- **淇**锛歚config.yaml` 閰?`dashboard.basic_auth.username + password_hash`锛坄plugins/dashboard_auth/basic` 鎻愪緵 `hash_password()`锛夈€?

### 4. Gateway 鎸佷箙鍖栨墭绠?

- 瀹瑰櫒鍘?entrypoint 鍙捣 dashboard锛実ateway 杩涚▼闅忓鍣ㄩ噸鍚涪澶便€?
- `hermes-base/entrypoint.sh` 鏂板 `start_gateway()`锛氬惎鍔?`python3.12 -m hermes_cli.main gateway run --no-supervise --replace --accept-hooks`锛堝鍣ㄥ唴 hermes CLI 鏄?`python3.12 -m hermes_cli.main`锛屾棤鐙珛 `hermes` 鍙墽琛屾枃浠讹級锛屽苟鐢?`.well-known/agent-card.json` 鎺㈡椿銆?
- 閲嶆柊鏋勫缓闀滃儚骞?`docker compose up -d --no-deps hermes`锛孉2A env 鐢熸晥銆?

### 5. 閰嶇疆涓庣鍙?

- compose hermes service 鏂板鐜鍙橀噺锛堟簮鑷?`.env`锛夛細
  - `A2A_HOST=0.0.0.0`锛堝厑璁?mailbus 璺ㄥ鍣ㄨ闂級
  - `A2A_BEARER_TOKEN=<闅忔満>`锛坆earer 閴存潈锛?
  - `A2A_PORT=9900`
- `config.yaml` `gateway.platforms.a2a`锛?
  - `enabled: true`锛宍extra.port: 9900`
  - `extra.agents`锛? 涓?served agents锛坄slug 鈫?profile` 璺敱锛屽 `lingzhao 鈫?profile: lingzhao`锛夛紝璁╁崟绔彛 9900 鍖哄垎 6 涓?agent 韬唤銆?
- **娉ㄦ剰**锛歝ompose 鍙妸 9120-9127 鏄犲皠鍒板涓伙紱9900 浠呭鍣ㄥ唴缃戯紙mailbus 璧?`hermes:9900`锛夛紝瀹夸富璁块棶闇€鍙﹁鏄犲皠鎴?`docker exec`銆?

## 浜屻€丮ailbus 渚?A2A 閫氶亾閰嶇疆

### 1. Agent 閫氶亾娉ㄥ叆

`store/config.json`锛堝涓讳笌瀹瑰櫒鍏变韩 bind mount锛? 涓?hermes_profile agents 澧炲姞锛?

```json
{
  "runtime": "hermes_profile",
  "channels": { "a2a": { "enabled": true }, "file_bus": { "enabled": true } },
  "endpoint": { "rpc_url": "http://hermes:9900/<slug>" },
  "auth": { "scheme": "bearer", "token_env": "A2A_BEARER_TOKEN" }
}
```

> `enrich_agent_channels` 鎸?`runtime`/`framework` 鍖归厤 `agent-channels.json` 榛樿鍊硷紱鍘?agents 鍙湁 `type`锛屽洜姝ゆ樉寮忓姞 `runtime` + endpoint + auth銆?

### 2. Token 娉ㄥ叆

- `docker-compose.override.yml` mailbus service 澧炲姞 `A2A_BEARER_TOKEN=${A2A_BEARER_TOKEN:-}`銆?
- 閲嶆柊 create mailbus 瀹瑰櫒鍚?env 鐢熸晥锛堝鍣ㄥ唴 `HttpA2AClient` 浠?`auth.token_env` 璇?token锛夈€?

### 3. 淇 A2A TaskStatus 鍏煎 bug锛堢湡瀹炵己闄凤級

- **闂**锛歮ailbus `a2a_standard.py` / `http_a2a.py` / `a2a_mapper.py` 鍋囧畾 `task.status` 鏄瓧绗︿覆锛坄"completed"`/`"input-required"`锛夛紝鑰?A2A v1.0 鏍囧噯杩斿洖 `TaskStatus` 瀵硅薄锛坄{"state": "TASK_STATE_COMPLETED", "message": {...}}`锛夆啋 `is_terminal`/`_poll_to_outcome`/`from_a2a_task` 鎶?`AttributeError: 'dict' object has no attribute 'lower'`銆?
- **淇**锛歚lib/core/a2a/a2a_mapper.py` 鏂板 `normalize_task_state(task)`锛屽吋瀹逛袱绉嶅舰寮忥紙鍚?`TASK_STATE_` 鍓嶇紑銆乣cancelled鈫抍anceled`銆乣input_required鈫抜nput-required`锛夛紝涓夊璋冪敤鐐圭粺涓€鏀圭敤銆?
- **鍥炲綊**锛氬涓?`pytest tests/test_a2a_mapper.py tests/test_a2a_poll.py tests/test_a2a_transport.py tests/test_a2a_cancel.py` 鈫?**11 passed, 7 skipped**銆?

## 涓夈€侀獙璇佺粨鏋?

### 1. A2A 绔偣锛堣法瀹瑰櫒锛?

浠?mailbus 瀹瑰櫒璋?`http://hermes:9900`锛?
- agent-card HTTP 200锛涙湭鎺堟潈 `message/send` HTTP **401**锛涙巿鏉冭繑鍥?200銆?
- default agent 绉掑洖 `PONG 鈥?鐏垫槶鍦ㄧ嚎`銆?
- slug 璺敱锛坄/lingjin`锛夋纭矾鐢卞埌 lingjin profile锛屽喎鍚姩绾?20s锛坄_forward_to_profile` spawn CLI锛夈€?

### 2. Mailbus Router 鍏ㄩ摼璺紙鐢熶骇妯″紡锛?

```
elapsed: 21.3s | ok: True
transport_used: a2a_standard    鈫?涓€娆℃垚鍔燂紝鏈檷绾?
a2a_task_id: task-78039447c7864048
attempts: [{channel: a2a_standard, attempt: 1, outcome: ok}]
step_result_path: /mailbus/store/msg-results/router-e2e-001/step-s1.json
step_result conclusion: done
```

### 3. 闄嶇骇璺緞

Hermes 涓嶅彲杈炬椂锛欰2A 閲嶈瘯 3 娆★紙backoff 2/5/10s锛夆啋 鑷姩闄嶇骇 file_bus 鎴愬姛浜や粯锛坄fallback_from: a2a_standard`锛夛紝绗﹀悎 `a2a-remote-adapter-spec.md` 璁捐銆?

## 涓壜疯ˉ銆丏ocker 鍐?agent 鍏ㄩ儴鍗囩骇鍒版渶鏂帮紙mailbus 鍙纭皟鐢級

鐢ㄦ埛瑕佹眰 docker 鍐呭惎鍔ㄧ殑 agent 涔熷崌鍒版渶鏂帮紝淇濊瘉 mailbus 璋冪敤姝ｇ‘銆?

### 1. 鐗堟湰鐜扮姸涓庡崌绾х洰鏍?

| Agent 瀹瑰櫒 | 鍗囩骇鍓?| 鍗囩骇鍚?| npm 鏈€鏂?| 璇存槑 |
|-----------|--------|--------|----------|------|
| `lingxiao`/`lingjian`锛坈odex锛?| codex 0.142.0 / gateway 0.1.5 | **codex 0.147.0** / **gateway 0.2.5** / codexapp 0.1.90 | 0.147.0 / 0.2.5 | 閲嶅缓 `docker-agents-codex` 闀滃儚 |
| `dali`锛坥pencode锛?| 1.17.9 | **1.18.15** | 1.18.15 | 閲嶅缓 `docker-agents-opencode` 闀滃儚 |
| `openclaw` | 2026.7.1-2 | 2026.7.1-2 | 2026.7.1-2 | 宸叉渶鏂帮紝鏃犻渶閲嶅缓 |
| `hermes` | v0.20.0 | v0.20.0 | 鈥?| 鏈細璇濇棭鍓嶅凡鍗囩骇 |

### 2. 鏋勫缓缁嗚妭

- codex/opencode 鐨?Dockerfile 閮芥敮鎸?`CODEX_VERSION`/`OPENCODE_VERSION` 鏋勫缓鍙傛暟锛堢┖ = 鏈€鏂帮級锛宑ompose 閲岄粯璁や紶绌?鈫?鐩存帴閲嶅缓鍗虫媺鏈€鏂般€?
- 鏋勫缓璧?WSL 缃戝叧浠ｇ悊 `http://172.20.128.1:7897`锛堝鍣ㄥ唴 npm 鍙揪锛夈€?
- **codex build context 缂?`bin/ttyd.x86_64`**锛氫粠杩愯涓殑 lingxiao 瀹瑰櫒 `docker cp` 鎻愬彇琛ュ洖锛坴1.7.7锛夈€?
- 鐢?`docker compose build --build-arg PROXY=... lingxiao lingjian dali` 閲嶅缓锛宍docker compose up -d` 鎹㈡柊瀹瑰櫒銆?
- 鏂伴暅鍍忓唴楠岃瘉锛歚codex-cli 0.147.0`銆乣opencode 1.18.15`锛屼笖瀹瑰櫒鍐?deepseek-gateway / UI / ttyd 鍏ㄩ儴姝ｅ父鎷夎捣銆?

### 3. 椤哄甫淇锛歴kills 鍚屾鑴氭湰 CRLF

瀹瑰櫒鏃ュ織鎶?`sync-opencode-framework-skill.sh: line 3: set: pipefail: invalid option name` 鈥斺€?Windows 鎹㈣绗︽薄鏌擄細
- `E:\ai_tools\mail\tools\sync-opencode-framework-skill.sh`
- `E:\ai_tools\mail\tools\sync-codex-agent-skills.sh`

宸?`sed -i 's/\r$//'` 杞?LF锛屽鍣ㄥ唴閲嶈窇楠岃瘉涓嶅啀鎶ラ敊銆?

### 4. 鍗囩骇鍚庤繛閫氭€ч獙璇?

- mailbus 鈫?hermes:9900 agent-card **HTTP 200**锛坉efault + `/lingzhao` slug 鍧囬€氾級銆?
- default agent `message/send` 绾?**8.5s** 杩斿洖 `TASK_STATE_COMPLETED`锛堝洖澶?鏀跺埌"锛夈€?
- mailbus 瀹瑰櫒 9814 API 姝ｅ父锛沜odex 瀹瑰櫒 3000 deepseek-gateway 鏈夊搷搴斻€?
- 鏃ュ織鏃?A2A/transport 寮傚父銆?

## 涓壜疯ˉ浜屻€丄2A 璋冪敤妯″紡璁捐妯″紡閲嶆瀯锛堜笉鍫嗗湪涓€涓柟娉曢噷锛?

### 1. 鍘熼棶棰?

`A2ATransport` 鎶?4 绉嶈皟鐢ㄦā寮忥紙鍚屾/寮傛/缁疆璇?缁窇锛? streaming/闈?streaming 鍙戦€佸垎鏀?+ 杞鐘舵€佸垎鏀叏閮ㄥ爢鍦?`dispatch_*`/`_send_only`/`_poll_to_outcome` 鍑犱釜澶ф柟娉曢噷锛屾柊澧炰竴绉嶈皟鐢ㄦ柟寮忓氨瑕佹敼涓€澶ф鏂规硶銆?

### 2. 閲嶆瀯鏂规

| 璁捐妯″紡 | 钀藉湴 |
|---------|------|
| **绛栫暐妯″紡** | 璋冪敤妯″紡锛歚A2ACallMode` 鎶借薄鍩虹被 + `SyncCallMode` / `AsyncCallMode` / `PollCallMode` / `ResumeCallMode` 鍥涗釜瀹炵幇 |
| **绛栫暐妯″紡** | 鍙戦€佹柟寮忥細`SendStrategy` 鎶借薄鍩虹被 + `StreamingFirstSendStrategy`锛坰treaming 浼樺厛澶辫触闄嶇骇锛? `PlainSendStrategy`锛堢洿鎺?SendMessage锛?|
| **妯℃澘鏂规硶** | `A2ACallMode.execute` 鍥哄畾銆屽噯澶?client 鈫?鍙戦€?鈫?鏀跺熬銆嶉鏋讹紝瀛愮被鍙鍐?`_prepare`/`_finish` 閽╁瓙 |
| **妯℃澘鏂规硶** | `PollOutcomeResolver.resolve` 鍥哄畾銆岄鏌?鈫?杞 鈫?鐘舵€佸垎鏀€嶉鏋讹紝`_handle_input_required`/`_build_terminal` 鐙珛瀹炵幇 |
| **闂ㄩ潰妯″紡** | `A2ATransport` 淇濈暀鏃у叕寮€鎺ュ彛锛坄dispatch_once`/`dispatch_async`/`poll_task`/`resume_after_resolve`/`cancel_task`锛夛紝鍐呴儴濮旀墭缁欑瓥鐣?|

### 3. 鏂板鏂囦欢

- `E:\ai_tools\mail\lib\transport\a2a_modes.py` 鈥斺€?璋冪敤妯″紡绛栫暐 + 鍙戦€佺瓥鐣?+ 宸ュ巶 `build_send_strategy()`
- `E:\ai_tools\mail\lib\transport\a2a_poll_resolver.py` 鈥斺€?杞缁撴灉瑙ｆ瀽锛堟ā鏉挎柟娉?+ 鐘舵€佸垎鏀媶鍒嗭級

### 4. 椤哄甫鍋ュ．鎬т慨澶?

`from_a2a_task` 鐨?`summary` 涔嬪墠鍙 `task.statusMessage`锛岃€?Hermes 鐨?A2A `TaskStatus` 杩斿洖 `status.message`锛坄Message` 瀵硅薄鍚?`parts[].text`锛夆啋 summary 鎭掍负绌恒€傛柊澧?`_status_message_text()` 涓ょ閮藉吋瀹癸紝瀹炴祴 summary 姝ｇ‘鍙栧埌銆屾敹鍒般€嶃€?

### 5. 鍥炲綊楠岃瘉

- 38 涓牳蹇?A2A 娴嬭瘯锛坱ransport/poll/streaming/cancel锛夊叏閫氳繃銆?
- 瀹瑰櫒鍐呯湡瀹?e2e锛氶噸鏋勫悗鐨?`dispatch_once` 鈫?hermes:9900 鈫?`ok: True` / `conclusion: done` / `transport_used: a2a_standard` / `summary: 鏀跺埌`銆?
- mapper golden fixture 娴嬭瘯 skip 涓虹幆澧冭祫浜х己澶憋紙鏃㈡湁闂锛屼笌鏈閲嶆瀯鏃犲叧锛夈€?

## 鍥涖€佹敼鍔ㄦ枃浠舵竻鍗?

| 鏂囦欢 | 鏀瑰姩 |
|------|------|
| `E:\ai_tools\mail\docker-agents\hermes-base\Dockerfile` | 婧愮爜 tar + editable 瀹夎锛涗繚鐣欐簮鐮?|
| `E:\ai_tools\mail\docker-agents\hermes-base\entrypoint.sh` | 鏂板 `start_gateway()` 鎵樼 gateway + `.no-bundled-skills` |
| `E:\ai_tools\mail\docker-agents\docker-compose.yml` | hermes service 鍔?A2A_HOST/TOKEN/PORT |
| `E:\ai_tools\mail\docker-agents\docker-compose.override.yml` | mailbus service 鍔?`A2A_BEARER_TOKEN` |
| `E:\ai_tools\mail\docker-agents\.env` | 鏂板 `A2A_HOST`/`A2A_BEARER_TOKEN`/`A2A_PORT` |
| `E:\hermes-data\.hermes\config.yaml` | `dashboard.basic_auth` + `gateway.platforms.a2a`锛坋nabled/port/served agents锛?|
| `E:\ai_tools\mail\store\config.json` | 6 涓?hermes agents 鍔?A2A 閫氶亾閰嶇疆 |
| `E:\ai_tools\mail\lib\transport\a2a_mapper.py` | `normalize_task_state()` + `from_a2a_task` 璋冪敤锛涙柊澧?`_status_message_text()`锛坰ummary 鍏煎 A2A Message 瀵硅薄锛?|
| `E:\ai_tools\mail\lib\transport\a2a_standard.py` | 鏀逛负闂ㄩ潰锛屽鎵?`a2a_modes` 绛栫暐锛沗_poll_to_outcome` 濮旀墭 `PollOutcomeResolver` |
| `E:\ai_tools\mail\lib\transport\http_a2a.py` | `is_terminal` 鐢?`normalize_task_state` |
| `E:\ai_tools\mail\lib\transport\a2a_modes.py` | **鏂板**锛氳皟鐢ㄦā寮忕瓥鐣ワ紙Sync/Async/Poll/Resume锛? 鍙戦€佺瓥鐣ワ紙Streaming/Plain锛? 宸ュ巶 |
| `E:\ai_tools\mail\lib\transport\a2a_poll_resolver.py` | **鏂板**锛氳疆璇㈢粨鏋滆В鏋愶紙妯℃澘鏂规硶 + input-required/terminal 鍒嗘敮锛?|
| `E:\ai_tools\mail\tools\sync-opencode-framework-skill.sh` | **淇** CRLF 鈫?LF |
| `E:\ai_tools\mail\tools\sync-codex-agent-skills.sh` | **淇** CRLF 鈫?LF |
| `E:\ai_tools\mail\docker-agents\codex-agent\bin\ttyd.x86_64` | **琛ュ洖**锛堜粠杩愯瀹瑰櫒鎻愬彇锛寁1.7.7锛?|
| `E:\ai_tools\mail\docker-agents\codex-agent\bin\ttyd.x86_64` | **git add 鍥哄寲**杩涚増鏈簱锛圓1-a锛?|
| `E:\ai_tools\mail\tools\sync-opencode-framework-skill.sh` | **鏀逛负 SoT 鎻愮ず**锛圓2锛屼笉鍐嶈皟骞界伒鑴氭湰锛?|
| `E:\ai_tools\mail\tools\sync-openclaw-framework-skill.sh` | **鏀逛负 SoT 鎻愮ず**锛圓2锛?|
| `E:\ai_tools\mail\tools\sync-all-agent-layers.py` | `_sync_framework_workspace` 鏀逛负 skip 鎻愮ず锛圓2锛?|
| `E:\ai_tools\mail\lib\adapters\ops\doctor_checks.py` | 鎻愮ず鏂囨鏀?SoT 璇存槑锛圓2锛?|
| `E:\ai_tools\mail\lib\transport\a2a_poll_resolver.py` | `poll_interval_sec` 鍏煎鍒楄〃/鏍囬噺锛圓3锛?|
| `E:\ai_tools\mail\config\mailbus\transport.template.json` | a2a 鍔?`poll_interval_sec`/`max_polls`锛圓3锛?|
| `E:\ai_tools\mail\store\config.json` | transport.a2a 鍔?poll/瓒呮椂閰嶇疆锛圓3锛?|
| `C:\Users\hopew\.wslconfig` | `memory=12GB`/`swap=4GB`锛圕6锛?|
| `E:\ai_tools\mail\tools\generate-compose-volumes.py` | A2A env 鍏ョ敓鎴愭簮 + 淇?`_to_compose_host` 鐩樼 bug + 淇?vault_hp 鍒ゆ柇锛圕7锛?|
| `E:\ai_tools\mail\docker-agents\mailbus\Dockerfile` | 鍔?pytest + `ARG PROXY`锛圕8锛?|
| `E:\ai_tools\mail\docker-agents\.env` | 鍔?`NODE_MODULES=/mnt/e/ai_tools/node_modules`锛坅gentmemory 淇锛?|
| `E:\ai_tools\mail\docker-agents\hermes-base\entrypoint.sh` | 鍘绘帀 `--help` 棰勬锛宲grep 鍏滃簳锛坓ateway 鑷姩鎷夎捣淇锛?|

## 涓壜疯ˉ涓夈€佷簩娆＄‘璁ら」澶勭悊缁撴灉锛?026-08-10 鍚屼細璇濓級

鍗囩骇瀹屾垚鍚庢暣鐞嗕簡 9 椤归渶浜屾纭鐨勯儴鍒嗭紝鐢ㄦ埛閫夋嫨銆屽叏閮ㄥ鐞?+ 涓€璧疯璁℃柟妗堛€嶏紝閫愰」纭鍚庤惤鍦帮細

### 1. A1-a锛歵tyd 鏋勫缓渚濊禆鍥哄寲锛堚渽锛?

- `codex-agent/bin/ttyd.x86_64`锛?.36MB锛寁1.7.7锛夊凡 `git add` 杩?mailbus 浠撳簱锛堟鍓?untracked锛屽共鍑€鐜閲嶅缓 codex 闀滃儚蹇呭け璐ワ級銆?
- 宸?staged锛屾湭 commit锛堢瓑鐢ㄦ埛鎸囩ず锛夈€?

### 2. A2锛歰pencode/openclaw skills 鍚屾澶辨晥锛堚渽锛?

- **鏍瑰洜**锛歚sync_framework_workspace_skills.py` 鏄€屽菇鐏佃剼鏈€嶁€斺€? 澶勫紩鐢紙opencode/openclaw/hermes/all 灞?doctor_checks锛変絾 git 浠庢湭杩借釜銆佹枃浠朵粠鏈瓨鍦ㄣ€?
- **鍐崇瓥**锛歴kills SoT = Vault junction锛坈ompose 鎸傝浇 `mail/skills` 鈫?Vault锛夛紝鍚屾闀滃儚閫昏緫涓?SoT 鏋舵瀯鍐茬獊锛屽垹闄ゅけ鏁堣皟鐢ㄣ€?
- 鏀瑰姩锛?
  - `tools/sync-opencode-framework-skill.sh` / `sync-openclaw-framework-skill.sh` 鈫?鏀逛负 SoT 鎻愮ず锛堜笉鍐嶈皟鐢ㄥ菇鐏佃剼鏈級
  - `tools/sync-all-agent-layers.py::_sync_framework_workspace` 鈫?鏀逛负 skip 鎻愮ず
  - `lib/adapters/ops/doctor_checks.py` 鈫?鎻愮ず鏂囨鏀逛负銆?sync 浠呬负闀滃儚缂撳瓨锛孲oT=Vault junction銆?

### 3. A3-a锛欰2A slug 鍐峰惎鍔ㄦ參锛堚渽锛?

- **鏍瑰洜**锛歴lug 璺敱 `_forward_to_profile` 鍐疯皟鐢?spawn 鍏ㄦ柊 CLI 杩涚▼锛?p 鎱?IO锛夛紝棣栨 20s+锛沝efault agent 璧?gateway 鍐?live session 8.5s銆?
- 淇锛堝蹇嶅喎鍚姩锛夛細
  - `lib/core/a2a/a2a_poll_resolver.py`锛歚poll_interval_sec` 鍏煎鍒楄〃/鏍囬噺锛堜慨澶?`float([2,5])` 娼滃湪 TypeError锛?
  - `config/mailbus/transport.template.json`锛歛2a 鍔?`poll_interval_sec: 2`銆乣max_polls: 90`
  - `store/config.json`锛堣繍琛屾椂 SoT锛夛細`transport.a2a` 鍔?`poll_interval_sec: 2`銆乣max_polls: 90`銆乣http_timeout_sec: 120`

### 4. C6-a锛歐SL/Docker 鍙嶅閲嶅惎锛堚渽锛?

- **鏍瑰洜纭**锛歐SL VM 鏁翠綋閲嶅惎锛坲ptime 292s 鏃跺叏閮ㄥ鍣ㄩ噸寤猴級锛岄潪 dockerd 鍗曠嫭銆侀潪 OOM锛堝唴瀛樺厖瓒筹級銆傜枒浼?Windows 渚цЕ鍙戙€?
- 淇锛歚C:\Users\hopew\.wslconfig` 鍔?`memory=12GB`銆乣swap=4GB`锛坄autoMemoryReclaim` 褰撳墠 WSL 鐗堟湰涓嶆敮鎸侊紝宸茬Щ闄わ級銆?
- **宸茬敓鏁?*锛歚MemTotal: 12.2GB`銆傞渶缁х画瑙傚療鏄惁杩樻湁閲嶅惎銆?

### 5. C7-a锛歝ompose sync 瑕嗙洊 A2A_BEARER_TOKEN锛堚渽锛屽惈闅愯棌 bug 淇锛?

- **鏍瑰洜**锛歚mailbus compose sync` 鏁翠綋閲嶅啓 `docker-compose.override.yml`锛岀敓鎴愭簮 `generate-compose-volumes.py` 鏃?A2A env銆?
- 淇锛?
  - 鐢熸垚婧?mailbus environment 鍧楀姞 `A2A_BEARER_TOKEN=${A2A_BEARER_TOKEN:-}`锛堥€忎紶锛屼笉纭紪鐮?secret锛?
  - **椤哄甫淇 `_to_compose_host` 鐩樼 bug**锛歐SL 涓?`Path("E:/...").resolve()` 鎶婄洏绗﹀綋鐩稿璺緞鎷奸敊锛坄/mnt/e/ai_tools/mail/E:/Obsidian/...`锛夛紝鏀逛负鍏堣瘑鍒樉寮忕洏绗﹀啀鏄犲皠 `/mnt/{drive}/...`
  - **淇 `AGENT_VAULT_ROOT` 鍒ゆ柇**锛歐SL 涓?Windows 鐩樼 `exists()` 鎭?False锛屾敼鐢ㄦ槧灏勫悗 `/mnt/{drive}` 璺緞鏍￠獙
- 楠岃瘉锛歚compose sync` 鐢熸垚姝ｇ‘璺緞锛圴ault 鎸傝浇榻愬叏锛? 淇濈暀 A2A env锛宍--check` 閫氳繃銆?

### 6. C8锛歮ailbus Dockerfile 鍥哄寲 pytest锛堚渽锛?

- `docker-agents/mailbus/Dockerfile`锛歚pip install PyYAML pytest`銆?
- **椤哄甫淇**锛欴ockerfile 鏀寔 `ARG PROXY`锛堜笅杞?docker CLI 璧颁唬鐞?`http://172.20.128.1:7897`锛夈€?
- 楠岃瘉锛氶噸寤洪暅鍍忓悗瀹瑰櫒鍐?`pytest 9.1.1` 鍥哄寲鐢熸晥銆?

### 7. 闄勶細agentmemory 瀹瑰櫒璧蜂笉鏉ワ紙NODE_MODULES 璺緞 bug锛屸渽锛?

- **鏍瑰洜**锛氫富 compose `${NODE_MODULES:-../node_modules}` 鐩稿 `docker-agents/` 瑙ｆ瀽涓?`mail/node_modules`锛堢┖鐩綍锛宒ocker 鑷姩鍒涘缓锛夛紝鐪熷疄 node_modules 鍦?`ai_tools/node_modules`銆?
- 淇锛歚docker-agents/.env` 鍔?`NODE_MODULES=/mnt/e/ai_tools/node_modules`锛涘垹闄よ寤虹┖ `mail/node_modules`銆?
- 楠岃瘉锛歛gentmemory 瀹瑰櫒 **healthy**銆?

### 8. 闄勶細hermes entrypoint 鑷姩鎷?gateway 澶辨晥锛堚渽锛?

- **鏍瑰洜**锛歚start_gateway` 閲?`"$PYTHON" -m hermes_cli.main --help` 棰勬鍦?9p 鎱㈢洏涓婂姞杞?CLI 鍗′綇/澶辫触 鈫?璺宠繃 gateway銆?
- 淇锛歚hermes-base/entrypoint.sh` 鍘绘帀 `--help` 棰勬锛屾敼鐢?pgrep + 绔彛鎺㈡祴鍏滃簳锛涚缉鐭杞帰娴?30鈫?5 娆°€?
- 楠岃瘉锛氶噸寤洪暅鍍?+ recreate 瀹瑰櫒锛宔ntrypoint **鑷姩鎷夎捣 gateway**锛?900 绾?141s 灏辩华锛堝惈 dashboard 鍚姩锛夛紝绔埌绔?A2A 401鈫?00 姝ｅ父銆?

## 涓壜疯ˉ鍥涖€乶8n 鍗囩骇锛?.76.1 鈫?2.33.7锛夛紙2026-08-10 鍚屼細璇濓級

鐢ㄦ埛閲嶇敵浼氳瘽杈圭晫锛氭湰浼氳瘽浠呮秹鍙婂悇 agent 灞傜粍浠讹紙agent / n8n / ttyd 绛夛級鐨勫崌绾т笌鍦?mailbus 涓殑閰嶇疆锛屼笉鏀?mailbus 鏈韩浠ｇ爜閫昏緫銆傜洏鐐圭‘璁ゅ敮涓€杩囨椂缁勪欢鏄?n8n锛岀敤鎴风‘璁ゅ崌绾с€?

### 1. 鐗堟湰涓庡喅绛?

- 鏈湴闀滃儚 `n8nio/n8n:1.76.1` 鈫?鏈€鏂?stable **2.33.7**锛?026-08-07 鍙戝竷锛夈€?
- n8n 鏄?mailbus 鍙€?sidecar锛坄docker-compose.n8n.yml`锛岀嫭绔?compose project锛岀鍙?5678锛夛紝涓嶅睘 docker-agents 涓绘爤銆?

### 2. 鍗囩骇鎵ц

- `docker-compose.n8n.yml` 闀滃儚 tag `1.76.1` 鈫?`2.33.7`銆?
- **鍗＄偣**锛氬畼鏂规簮 `docker pull` 鍙嶅 EOF锛圕lash 浠ｇ悊瀵?Docker CloudFront 澶?blob 娴佷腑鏂紝鍚屼竴灞?`3130b12f9908` 杩炵画澶辫触锛夈€?
- **瑙ｆ硶**锛氭敼鐢?DaoCloud 鍔犻€熸簮 `docker pull docker.m.daocloud.io/n8nio/n8n:2.33.7`锛?0s 鎴愬姛锛夛紝retag 涓?`n8nio/n8n:2.33.7`銆?
- `docker compose -f docker-compose.n8n.yml up -d` 鍒涘缓瀹瑰櫒锛堟棫 `n8n-data` 鍗蜂繚鐣欙紝workflow 鏁版嵁涓嶄涪锛夈€?

### 3. 楠岃瘉

- 瀹瑰櫒 `docker-agents-n8n-1` **healthy**锛宍n8n --version` 鈫?**2.33.7**銆?
- `/healthz` 鈫?200锛沵ailbus 瀹瑰櫒鍐呯粡 `host.docker.internal:5678` 璁块棶 鈫?200銆?
- **閰嶇疆鏃犻渶璋冩暣**锛歮ailbus 渚?`N8N_PUBLISH_WEBHOOK_URL=http://127.0.0.1:5678/...` 鏄粰**瀹夸富渚?* Windows mailbus 鐢ㄧ殑锛坄lib/adapters/integrations/n8n/wsl_bridge.py` 鏈?WSL curl 鍏滃簳锛屼笓娌?Windows鈫扺SL Docker localhost 涓嶅彲杈撅級锛屽睘鏃㈡湁璁捐锛屼笉灞炴湰浼氳瘽鏀瑰姩鑼冨洿銆?

### 4. 鏀瑰姩鏂囦欢

| 鏂囦欢 | 鏀瑰姩 |
|------|------|
| `E:\ai_tools\mail\docker-agents\docker-compose.n8n.yml` | n8n 闀滃儚 `1.76.1` 鈫?`2.33.7` |

## 浜斻€侀仐鐣?/ 娉ㄦ剰浜嬮」

1. **served agents 鍐峰惎鍔ㄧ害 20s**锛歴lug 璺敱璧?`_forward_to_profile` spawn CLI session锛屾瘮 default agent 鎱€傝嫢闇€绉掔骇鍝嶅簲锛屽彲淇濇寔 default agent锛堝叡浜竴涓韩浠斤級锛屾垨浼樺寲 hermes profile 棰勭儹銆?
2. **Docker daemon 鏇炬暣浣撻噸鍚?*锛?3:34:43锛岄潪鏈泦鎴愬鑷达級锛氶噸鍚湡闂存墍鏈夊鍣ㄩ噸寤恒€傞泦鎴愭湰韬棤宕╂簝寰幆锛坄RestartCount=0`锛夈€?
3. **compose 鏂囦欢鐢?`mailbus compose sync` 鐢熸垚**锛氭墜宸ユ敼鍔ㄥ彲鑳借瑕嗙洊锛涘闇€鎸佷箙鍖栵紝搴斿悓姝ヤ慨鏀圭敓鎴愭簮鎴?override銆?
4. **瀹夸富璁块棶 9900 涓嶄究**锛氬闇€瀹夸富 curl/璋冭瘯锛屽彲鍦?override 鍔?`9900:9900` 鏄犲皠銆?
5. **mailbus 鐜版湁 hermes file_bus push 鍛戒护**锛坄docker exec hermes chat --profile ...`锛変粛鍙敤锛孯outer 鐜板湪浼樺厛 A2A锛屽け璐ユ墠闄嶇骇 file_bus鈥斺€斾笉褰卞搷鍘熼€氶亾銆?
6. **codex 闀滃儚鏋勫缓渚濊禆 `bin/ttyd.x86_64`**锛氳鏂囦欢涓嶅湪 git锛坆uild context 閲岃蹇界暐/鍒犻櫎锛夛紝閲嶅缓 codex 闀滃儚鍓嶉渶鍏堜粠杩愯瀹瑰櫒 `docker cp` 琛ュ洖锛堣瑙佹湰鎶ュ憡"涓壜疯ˉ"锛夈€?
7. **skills 鍚屾鑴氭湰 CRLF 澶嶅彂椋庨櫓**锛氳嫢鍦?Windows 渚х紪杈?`.sh` 鍚庡悓姝ュ埌 WSL锛屽彲鑳介噸鏂板紩鍏?`\r`锛屾敞鎰?`git core.autocrlf` 鎴栨彁浜ゆ椂淇濇寔 LF銆?

## 鍏宠仈鏂囨。

- [[Agent/01-mailbus/016-docs/0161-architecture/a2a-remote-adapter-spec]]锛坢ailbus A2A 璁捐瑙勮寖锛?
- [[Agent/01-mailbus/016-docs/0161-architecture/a2a-compliance-spec]]
- [[Agent/01-mailbus/016-docs/0161-architecture/a2a-field-mapping]]
- [[Agent/01-mailbus/017-plans/0173-plans/2026-07-31-mailbus-layered-refactor-master]]
