# adapters.runtime — run_target 分发器与四端适配器

> Arch1：Dispatcher + PathPort；CredDelivery 已接 env 同步；Probe/Launch 后置。

| 模块 | 职责 |
|------|------|
| `dispatcher.py` | `run_target` → Adapter；框架矩阵校验；旧枚举兼容 |
| `adapters`/`paths.py` | windows / wsl / linux / docker Path |
| `distro.py` | Linux DistroProfile（ubuntu / centos 族） |
| `boundary.py` | 跨边界（Windows↔WSL 测试床） |
| `cred_delivery.py` | secrets → OPENCLAW/CODEX/HERMES env；实例 host/port 改写 URL |
