# 大屏密钥文件保管说明

面向运维与开发，说明 `screen-secrets.json` 的敏感级别、存储要求、轮换与泄露处置。

## 1. 适用范围

| 项 | 内容 |
| --- | --- |
| 文件 | `<data_dir>/screen-secrets.json`（默认 `data/screen-secrets.json`） |
| 生成 | `python tools/backfill_screen_secrets.py --via-api --token <管理员Token>` |
| 内容 | `base_url`、`screens[]`，每项含 `screen_id`、`name`、`secret` |
| 关联接口 | `POST /api/public/collab/screens/{id}/heartbeat`、`POST /api/public/collab/screens/{id}/leave` |

## 2. 敏感级别

`secret` 是**明文凭证**，持有即等同于该大屏的写入身份：

- 可发送心跳，把大屏置为在线并改写 `floor_id` / `seat_id` 归属；
- 可发送离线，把大屏置为离线（造成大屏"消失"的 DoS 效果）；
- 无需其他认证即可调用，属于公开端点上的唯一凭据。

因此按「与访问令牌同级」对待：**不入库、不外发、不贴聊天/工单/文档**。

> 接口侧的保护边界：`GET /api/collab/screens` 列表不回显 `secret`；公开重复登记（`POST /api/public/collab/screens`）也不回显，只有管理员登记接口会返回。该文件是唯一集中留档点。

## 3. 存储要求

1. **不入版本库**：仓库 `.gitignore` 已忽略 `data/`。若用 `--out` 指到其他路径，需自行确认被忽略；建议追加显式规则：

   ```gitignore
   **/screen-secrets.json
   ```

2. **最小权限**（Windows，按实际运行账号调整）：

   ```powershell
   icacls "E:\ai_tools\mailbus\data\screen-secrets.json" /inheritance:r /grant:r "$env:USERNAME:(R,W)"
   ```

   Linux/macOS：`chmod 600`，属主为服务账号。

3. **禁用同步盘公开链接**：不要放在带公开分享链接的网盘/协作目录。

4. **备份加密**：如需备份，使用带口令的加密归档（如 `7z a -p ...`）或放入密钥管理系统；禁止明文压缩包随其他备份一起流转。

5. **传输**：仅通过加密通道（SSH/HTTPS/受控跳板）传递，不使用即时通讯明文发送。

## 4. 使用方式

该文件只对「固定 `screen_id` 的可配置大屏」有意义：

- 页面自动登记的大屏每次加载都会生成新的随机 `screen_id`，刷新即换密钥，无需保留文件；
- 固定大屏（如墙面设备）应通过管理员登记接口创建，并在设备侧持久化 `screen_id` 与 `secret`，心跳/离线时携带 `{"secret": "..."}`。

## 5. 轮换与泄露处置

接口不支持"指定新密钥"，轮换通过「清空后重新登记」完成：

1. 计算目标大屏的新密钥（任选其一）：
   - 删除该大屏记录后，用管理员登记接口重新登记（会生成新 `secret` 并回显）；
   - 或停服后执行 `UPDATE collab_screens SET secret = NULL WHERE screen_id = '...';`，再运行回填脚本重新生成。
2. 更新设备侧配置与 `screen-secrets.json`；
3. 旧密钥随记录覆盖即失效，无需额外吊销；
4. 期间产生的异常心跳/离线请求应在访问日志中排查是否来自未知来源。

泄露后的最小动作：**立即轮换该 `screen_id` 的密钥**，并检查该大屏的 `floor_id` / `seat_id` 是否被篡改。

## 6. 验证清单

```powershell
$uri = 'http://127.0.0.1:9814/api/public/collab/screens/<screen_id>/heartbeat'

# 不带密钥：应为 403
try {
  Invoke-WebRequest -Method POST -ContentType 'application/json' `
    -Body '{"floor_id":"f1"}' -Uri $uri -UseBasicParsing | Out-Null
} catch { $_.Exception.Response.StatusCode.value__ }

# 带正确密钥：应为 200
try {
  Invoke-WebRequest -Method POST -ContentType 'application/json' `
    -Body '{"floor_id":"f1","secret":"<secret>"}' -Uri $uri -UseBasicParsing | Out-Null
  '200'
} catch { $_.Exception.Response.StatusCode.value__ }
```

预期依次输出 `403`、`200`。

## 7. 生命周期

- 回填完成后文件即可删除——页面刷新会重新登记并自动获取新密钥；
- 仅在需要长期固定 `screen_id` 的设备场景才需要保留；
- 人员/设备交接、环境重建时，按「凭证交接」流程重新生成，不复用旧文件。
