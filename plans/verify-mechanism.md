# 完成验证机制

> 防止 agent auto-ack 但实际没做的情况。
> 每个角色提交"完成"后，mailbus 验证其产出，确认无误后才推进流程。

---

## 各角色的验证规则

| 角色 | 结论 | 验证方式 | 验证不通过的处理 |
|------|------|----------|-----------------|
| **开发工程师** | done | 检查 git diff，确认有代码改动 | 退回，要求重新提交 |
| **审查官** | pass | 检查 review report 中是否有实质审查内容（如 issues 列表、结论依据） | 退回，要求补充审查内容 |
| **测试工程师** | pass | 手动或自动跑 pytest，验证测试通过 | 退回，要求重新测试 |
| **调度员** | dispatched | 检查是否真的有派发消息给下一步角色 | 退回，要求重新派发 |
| **验收员** | approved | 检查前面所有步骤是否都已完成（审查通过+测试通过） | 退回，要求补全前置步骤 |

---

## 具体验证实现

### 开发完成验证

当收到开发工程师的 `conclusion: done` 时：

```python
def verify_dev_done(task_id, report):
    """验证开发工程师是否真的改了代码"""
    # 1. 检查 git diff
    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD~1"], 
        capture_output=True, text=True, cwd=REPO_DIR
    )
    if not result.stdout.strip():
        # 没有代码改动 → 退回
        return False, "未检测到代码改动，请确认是否真的完成了开发"
    
    # 2. 检查自测
    if report.get("details", {}).get("self_test") != "pass":
        return False, "自测未通过，请确认测试全部pass后再提交"
    
    return True, None
```

### 审查完成验证

当收到审查官的 `conclusion: pass` 时：

```python
def verify_review_done(task_id, report):
    """验证审查官是否真的做了审查"""
    details = report.get("details", {})
    issues = details.get("issues", [])
    
    # 1. 检查是否有审查内容
    if not details.get("review_tool"):
        return False, "审查报告缺少审查工具信息（review_tool），请补充"
    
    # 2. 检查是否有审查结论的依据
    if not details.get("passed_checks") and not issues:
        # 既没有说明检查了哪些项，也没有发现问题 → 可能是空审查
        return False, "审查报告缺少检查项记录（passed_checks），请补充"
    
    return True, None
```

### 测试完成验证

当收到测试工程师的 `conclusion: pass` 时：

```python
def verify_test_done(task_id, report):
    """验证测试工程师是否真的做了测试"""
    details = report.get("details", {})
    
    # 1. 检查是否有逐项测试结果
    if not details.get("results"):
        return False, "测试报告缺少逐项测试结果（results），请补充"
    
    # 2. 检查 passed + failed 数量是否对得上
    total = details.get("total", 0)
    passed = details.get("passed", 0)
    failed = details.get("failed", 0)
    if total != passed + failed:
        return False, f"测试总数({total})与通过+失败({passed}+{failed})不一致"
    
    # 3. 如果有 failed，conclusion 应该是 fail 而不是 pass
    if failed > 0:
        return False, f"有 {failed} 项测试失败，结论应为 fail 而不是 pass"
    
    return True, None
```

---

## 验证不通过的后果

| 次数 | 处理方式 |
|------|----------|
| 第 1 次 | 退回给当前角色，要求补充/重做 |
| 第 2 次 | 退回 + 抄送调度员（小七）关注 |
| 第 3 次 | 升级给方案设计师（灵昭）+ 标记该角色"需关注" |

```python
def handle_verify_failed(task_id, current_step, fail_reason, attempt):
    """验证不通过的处理"""
    if attempt == 1:
        # 第一次：退回重做
        send_message(to=current_step.execute_person, 
                     content=f"验证不通过：{fail_reason}，请补充后重新提交")
    elif attempt == 2:
        # 第二次：退回 + 通知调度员
        send_message(to=current_step.execute_person,
                     content=f"验证不通过（第2次）：{fail_reason}，请补充")
        send_message(to="xiaoqi",
                     content=f"注意：{current_step.execute_person} 的验证已失败2次")
    elif attempt >= 3:
        # 第三次：升级给灵昭
        send_message(to="lingzhao",
                     content=f"{current_step.execute_person} 的验证已失败3次，请关注")
        mark_agent_attention(current_step.execute_person)
```

---

## 灵巡巡检新增：进程健康检查

灵巡巡检时除了看任务链，还要检查关键进程是否在线：

```python
CRITICAL_PROCESSES = {
    "mailbus":      { "port": 9812, "type": "port" },
    "lingzhao":     { "port": 9120, "type": "port" },
    "lingjin":      { "port": 9121, "type": "port" },
    "lingxi":       { "port": 9122, "type": "port" },
    "lingjian":     { "port": 9123, "type": "port" },
    "lingyan":      { "port": 9124, "type": "port" },
    "lingxun":      { "port": 9125, "type": "port" },
    "xiaoqi":       { "port": 18789, "type": "port" },
    "yige":         { "port": 18790, "type": "port" },
}

def check_process_health():
    dead = []
    for name, info in CRITICAL_PROCESSES.items():
        if info["type"] == "port":
            if not is_port_listening(info["port"]):
                dead.append(name)
    return dead
```

如果发现某个进程挂了，灵巡的巡检报告标注异常，同时尝试重启。

---

## 验证+巡检双保险后的全链路

```
开发提交 done
  ↓ mailbus 验证 git diff + 自测
  ↓ 通过 → 到审查
  ↓ 不通过 → 退回开发（抄送小七）
  
审查提交 pass
  ↓ mailbus 验证审查内容完整性
  ↓ 通过 → 到测试
  ↓ 不通过 → 退回审查（抄送小七）
  
测试提交 pass
  ↓ mailbus 验证测试结果一致性
  ↓ 通过 → 到验收
  ↓ 不通过 → 退回测试（抄送小七）
  
验收提交 approved
  ↓ mailbus 验证前置步骤全部完成
  ↓ 通过 → 完成
  ↓ 不通过 → 退回验收

灵巡每15分钟巡检：
  - 检查所有任务链有没有卡住的步骤（超时10分钟）
  - 检查所有关键进程是否在线
  - 出巡检报告
```
