"""角色流转规则 — 根据角色+结论自动决定下一步角色。"""

# 流转规则表：(当前角色, 结论) → 下一步角色
# None = 没有下一步（任务完成）
_FLOW_RULES = {
    # 开发工程师
    ("开发工程师", "done"):      "审查官",
    ("开发工程师", "blocked"):   "方案设计师",
    
    # 审查官
    ("审查官", "pass"):          "测试工程师",
    ("审查官", "fail"):          "开发工程师",
    
    # 测试工程师
    ("测试工程师", "pass"):      "验收员",
    ("测试工程师", "fail"):      "开发工程师",
    
    # 验收员
    ("验收员", "approved"):      None,  # 完成
    ("验收员", "rejected"):      "开发工程师",
    
    # 调度员
    ("调度员", "dispatched"):    "开发工程师",
    ("调度员", "approved"):      None,
    
    # 方案设计师
    ("方案设计师", "approved"):  "调度员",
    ("方案设计师", "done"):      "调度员",
    ("方案设计师", "need_research"): "技术研究员",
    
    # 安全审计师
    ("安全审计师", "pass"):      "审查官",
    ("安全审计师", "fail"):      "开发工程师",
    
    # 技术研究员
    ("技术研究员", "done"):      "方案设计师",
    
    # 巡检官
    ("巡检官", "done"):          None,
    ("巡检官", "warning"):       "方案设计师",
    
    # 运营
    ("运营", "done"):            None,
}

# 角色→可执行人映射
_ROLE_MAP = {
    "方案设计师": ["lingzhao"],
    "调度员":    ["xiaoqi"],
    "开发工程师": ["lingxiao", "dali"],
    "审查官":    ["lingjian"],
    "测试工程师": ["lingyan"],
    "安全审计师": ["lingjin"],
    "技术研究员": ["lingxi"],
    "巡检官":    ["lingxun"],
    "运营":      ["yige"],
    "验收员":    ["xiaoqi"],
}


def get_next_role(current_role: str, conclusion: str):
    """根据当前角色和结论获取下一步角色。"""
    return _FLOW_RULES.get((current_role, conclusion))


def pick_person_for_role(role: str):
    """根据角色分配具体执行人。"""
    candidates = _ROLE_MAP.get(role, [])
    # TODO: 在线检测 + 负载均衡
    return candidates[0] if candidates else None


def get_online_status():
    """返回各角色的在线状态（占位，后续实现真实检测）。"""
    return {role: persons for role, persons in _ROLE_MAP.items()}
