# 各 Agent CLI 非交互模式调研

## Hermes Agent（灵昭、灵瑾）
- **命令**: `hermes chat -q "<消息>" -Q`
- **说明**: `-q/--query` 为非交互单次查询模式，`-Q` 静默模式（不要 banner/动画）
- **带 profile**: `hermes chat -q "<消息>" -Q --profile <name>`
- **带 skill**: `hermes chat -q "<消息>" -Q -s <skill>`
- **特点**: 原生支持，返回码 0 表示成功，可通过 stdout 获取回复
- **✅ 可用** — 灵昭、灵瑾都能用

## OpenClaw（小七、一哥）
- **命令**: `openclaw agent --local --message "<消息>" --json`
- **说明**: `--local` 表示本地运行，`--message` 传消息，`--json` 输出 JSON
- **特点**: 通过 gateway 的 agent 路由，可以指定 agent ID
- **带 workspace**: `openclaw agent --local --agent xiaoqi --message "<消息>" --json`
- **✅ 可用** — 小七、一哥都能用

## Cline CLI（灵霄）
- **命令**: `cline <prompt> --provider openai-compatible -s "<skill>"`
- **说明**: 直接传 prompt 作为位置参数就是非交互模式，自动 auto-approve
- **限制**: 需要 skill/system prompt 来注入身份（目前用 -s 参数传文件内容）
- **✅ 可用** — 灵霄可以用

## OpenCode（大力）
- **命令**: `opencode run <消息> --dangerously-skip-permissions`
- **说明**: `run` 子命令专门用于非交互式运行
- **特点**: 支持 `--agent` 指定 agent，`--model` 指定模型
- **限制**: `--dangerously-skip-permissions` 不能省（否则会等待用户确认）
- **✅ 可用** — 大力可以用

## Aider（大壮）
- **命令**: `/mnt/e/ai_tools/aider/.venv/bin/aider --message "<消息>" --yes-always`
- **说明**: `--message` 非交互模式，完成后退出
- **特点**: `--yes-always` 自动确认所有操作
- **⚠️ 注意**: Aider 的 `--message` 传的是编码指令不是文本通知。对于纯通知场景，aider 启动后可能会尝试修改文件
- **部分可用** — 通知类消息不适合用 aider 的 `--message`，建议大壮走纯文件通信
