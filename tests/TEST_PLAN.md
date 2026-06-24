# ziyan-mailbus 测试计划

## 现有测试（3 个文件，19 个用例）
- tests/test_scanner.py — 扫描逻辑
- tests/test_ack_handler.py — ack 处理
- tests/test_archiver.py — 归档逻辑

## 需要新增的测试文件

### 1. tests/test_models.py — 数据模型
- [ ] Message 创建 + 默认值
- [ ] MsgType 枚举完整
- [ ] MsgType.default_action() 每个 type 的正确 action
- [ ] Message action/forward_chain 自动填充 (__post_init__)
- [ ] Message to_dict / from_dict 序列化反序列化
- [ ] Inbox to_dict / from_dict
- [ ] 缺 id 自动生成
- [ ] 未知字段过滤

### 2. tests/test_pusher.py — 推送逻辑
- [x] resolve_cli_chain 基础替换（见 tests/test_task_completion.py）
- [ ] MODEL 占位符替换（有值/无值）
- [ ] PROVIDER 占位符替换
- [ ] 多模型 fallback 链生成
- [ ] resolve_cli 函数（单条/链）
- [ ] push_messages（mock CLI）

### 3. tests/test_tracker.py — 任务追踪
- [ ] TaskTracker.create 创建任务
- [ ] TaskTracker.get 读取任务
- [ ] TaskTracker.update_status 状态更新
- [ ] TaskTracker.add_hop 追加追踪链
- [ ] TaskTracker.increment_reminder 催办递增
- [ ] TaskTracker.check_reminders 催办触发
- [ ] 催办超限自动 timeout

### 4. tests/test_heartbeat.py — 心跳检测
- [ ] load_status / save_status
- [ ] is_online（在线/离线/无记录）
- [ ] check_agentmemory（mock HTTP）
- [x] test_memory_bridge_dual — SQLite 主写 + AM 辅写、marker v2 迁移（见 tests/test_memory_bridge_dual.py）
- [ ] check_inbox_size（正常/告警）
- [ ] check_disk_space（正常/告警）
- [ ] ping_agent（mock subprocess）
- [ ] ping_agent_with_report（自检上报解析）

### 5. tests/test_search.py — 消息检索
- [ ] index_message 写入索引
- [ ] search 全文搜索
- [ ] search 按 from/to/type/status 过滤
- [ ] scan_and_index 批量索引

### 6. tests/test_alerter.py — 告警系统
- [ ] push_alert 记录告警
- [ ] push_alert 推送到管理员 inbox
- [ ] get_recent_alerts 获取最近告警

### 7. tests/test_utils.py — 工具函数
- [ ] json_read / json_write（正常/损坏修复/备份）
- [ ] build_message（基础/with forward_to/with task）
- [ ] generate_msg_id 格式
- [ ] resolve_paths
- [ ] log_error
