# 大屏身份与密钥保管说明

> 2026-11-25 · 已按「设备级持久化 + 哈希存储 + Header 传输」更新。
> 旧的 `screen-secrets.json` 回填方案已废止：库内只存哈希，服务端无法再生成或找回明文，该文件不再作为密钥留档点。

## 1. 模型

| 项 | 内容 |
| --- | --- |
| 身份 | `screen_id`，`/twin` 首次打开自动登记生成 |
| 密钥 | `screen_secret`，仅在**登记响应**返回一次明文 |
| 服务端存储 | `collab_screens.secret_hash`（不可逆哈希）；列表、心跳、配置接口均不回显 |
| 设备存储 | `localStorage["mailbus.screen"] = { screen_id, secret }`，跨标签、刷新、关浏览器与重启复用 |
| 传输 | 心跳/离线请求头 `X-Screen-Secret` |
| 接口 | `POST /api/public/collab/screens`、`POST .../{id}/heartbeat`、`POST .../{id}/leave` |

## 2. 敏感级别

`secret` 持有即等同于该大屏的写入身份：

- 可发送心跳，把大屏置为在线并改写 `floor_id` / `seat_id` 归属；
- 可发送离线，把大屏置为离线（造成大屏"消失"的 DoS 效果）；
- 公开端点上的唯一凭据，无需其他认证。

因此与访问令牌同级：**不贴聊天/工单/文档、不写入 URL、不打日志、不截图**。由于库内只有哈希，明文只存在于设备本地和登记时的一次性响应，**无法从服务端找回**。

## 3. 设备侧要求

1. 固定墙屏必须允许 `localStorage` 持久化；隐私模式/无痕窗口每次都会按新屏登记，接管配置会丢失。
2. 设备交接、环境重建时不要复制旧 `secret`：删除设备本地记录后重新登记，再重新接管配置。
3. `?preview=1` 只读已发布配置，不登记、不发心跳、不持有身份。

## 4. 存储与网络

1. **不入版本库**：密钥不落任何服务端明文文件；设备侧的浏览器存储由设备自身保护。
2. **最小权限**：设备使用独立浏览器配置/账号，禁止多人共用会同步 `localStorage` 的账号。
3. **传输**：仅通过加密通道（HTTPS/受控内网）传递，禁止即时通讯明文发送。

## 5. 轮换与泄露处置

接口不支持"指定新密钥"，轮换流程：

1. 确认目标大屏离线（在线删除返回 409）；
2. 管理端删除该屏幕记录；
3. 在设备上清除 `localStorage["mailbus.screen"]`；
4. 设备重新打开 `/twin` 自动登记，获得新 `screen_id` 与一次性 `secret`；
5. 管理端重新接管：重命名、绑定团队、恢复布局/主题/分辨率并发布。

泄露后的最小动作：**立即按上述流程轮换该屏**，并在访问日志中排查异常心跳/离线来源，检查 `floor_id` / `seat_id` 是否被篡改。

## 6. 验证清单

```powershell
$uri = 'http://127.0.0.1:9814/api/public/collab/screens/<screen_id>/heartbeat'

# 不带密钥：应为 403
try {
  Invoke-WebRequest -Method POST -ContentType 'application/json' `
    -Body '{"floor_id":"f1"}' -Uri $uri -UseBasicParsing | Out-Null
} catch { $_.Exception.Response.StatusCode.value__ }

# 带正确密钥（Header）：应为 200
try {
  Invoke-WebRequest -Method POST -ContentType 'application/json' `
    -Headers @{ 'X-Screen-Secret' = '<secret>' } `
    -Body '{"floor_id":"f1"}' -Uri $uri -UseBasicParsing | Out-Null
  '200'
} catch { $_.Exception.Response.StatusCode.value__ }
```

预期依次输出 `403`、`200`。

## 7. 生命周期

- 心跳 30 秒；60 秒无心跳判离线。
- 仅**从未被管理端接管**且离线超过 30 天的自动登记屏幕会被清理；已接管或已发布屏幕不自动删除。
- 管理端可删除离线屏幕；删除不影响布局、消息与历史。
- `screen_id` / `secret` 没有任何服务端明文备份，丢失即按新屏重新登记。
