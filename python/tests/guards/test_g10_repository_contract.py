"""G10 仓储契约守卫：core 协议必须有 SQLite 实现，且成员不能漏。

背景：mailbus 的持久化边界是 core/<context>/ports.py 里的 Protocol；
SQLite 只是其中一种实现，未来可替换为 MySQL/ES/向量库。
协议新增方法而实现漏改时，这里直接失败（运行时不报错的隐患）。
"""

from __future__ import annotations

import ast
import sys
from importlib import import_module
from pathlib import Path

_GUARDS = Path(__file__).resolve().parent
sys.path.insert(0, str(_GUARDS))
sys.path.insert(0, str(_GUARDS.parents[1]))

from _scan import REPO_ROOT  # noqa: E402

CORE = REPO_ROOT / "python" / "mailbus" / "core"
SQLITE = "mailbus.adapters.persistence.sqlite"

# 协议 (模块, 类) -> SQLite 实现 (模块, 类)
CONTRACTS: dict[tuple[str, str], tuple[str, str]] = {
    ("mailbus.core.agents.ports", "AgentRepository"): (f"{SQLITE}.agents_repo", "SqliteAgentRepository"),
    ("mailbus.core.approval.ports", "ApprovalRepository"): (f"{SQLITE}.approval_repo", "SqliteApprovalRepository"),
    ("mailbus.core.collab.ports", "ScreenRepository"): (f"{SQLITE}.collab_repo", "SqliteScreenRepository"),
    ("mailbus.core.collab.ports", "PairRepository"): (f"{SQLITE}.collab_repo", "SqlitePairRepository"),
    ("mailbus.core.identity.ports", "EmployeeRepository"): (f"{SQLITE}.identity_repo", "SqliteEmployeeRepository"),
    ("mailbus.core.identity.ports", "InviteRepository"): (f"{SQLITE}.identity_repo", "SqliteInviteRepository"),
    ("mailbus.core.identity.ports", "SessionRepository"): (f"{SQLITE}.identity_repo", "SqliteSessionRepository"),
    ("mailbus.core.identity.ports", "BootstrapRepository"): (f"{SQLITE}.identity_repo", "SqliteBootstrapRepository"),
    ("mailbus.core.messaging.ports", "MessageRepository"): (f"{SQLITE}.messaging_repo", "SqliteMessageRepository"),
    ("mailbus.core.metrics.ports", "MetricRuleRepository"): (f"{SQLITE}.metrics_repo", "SqliteMetricRuleRepository"),
    ("mailbus.core.metrics.ports", "MetricLayoutRepository"): (f"{SQLITE}.metrics_repo", "SqliteMetricLayoutRepository"),
    ("mailbus.core.metrics.ports", "MetricReportRepository"): (
        f"{SQLITE}.metrics_report_repo",
        "SqliteMetricReportRepository",
    ),
    ("mailbus.core.ops.ports", "OpsRepository"): (f"{SQLITE}.ops_repo", "SqliteOpsRepository"),
    ("mailbus.core.org.ports", "TeamRepository"): (f"{SQLITE}.org_repo", "SqliteTeamRepository"),
    ("mailbus.core.org.ports", "PositionRepository"): (f"{SQLITE}.org_repo", "SqlitePositionRepository"),
    ("mailbus.core.org.ports", "SeatRepository"): (f"{SQLITE}.org_repo", "SqliteSeatRepository"),
    ("mailbus.core.org.ports", "RoleRepository"): (f"{SQLITE}.org_repo", "SqliteRoleRepository"),
    ("mailbus.core.skills.ports", "SkillPackageRepository"): (f"{SQLITE}.skills_repo", "SqliteSkillPackageRepository"),
    ("mailbus.core.skills.ports", "SkillBindingRepository"): (f"{SQLITE}.skills_repo", "SqliteSkillBindingRepository"),
    ("mailbus.core.workflow.ports", "WorkflowDefinitionRepository"): (
        f"{SQLITE}.workflow_repo",
        "SqliteWorkflowDefinitionRepository",
    ),
    ("mailbus.core.workflow.ports", "WorkflowVersionRepository"): (
        f"{SQLITE}.workflow_repo",
        "SqliteWorkflowVersionRepository",
    ),
    ("mailbus.core.workflow.ports", "WorkflowGraphRepository"): (
        f"{SQLITE}.workflow_graph_repo",
        "SqliteWorkflowGraphRepository",
    ),
    ("mailbus.core.workflow.ports", "TaskRepository"): (f"{SQLITE}.workflow_repo", "SqliteTaskRepository"),
    ("mailbus.core.workflow.ports", "TaskRunRepository"): (f"{SQLITE}.task_repo", "SqliteTaskRunRepository"),
    ("mailbus.core.workflow.ports", "TaskArtifactRepository"): (
        f"{SQLITE}.task_repo",
        "SqliteTaskArtifactRepository",
    ),
    ("mailbus.core.workflow.ports", "TaskEscalationRepository"): (
        f"{SQLITE}.task_repo",
        "SqliteTaskEscalationRepository",
    ),
    ("mailbus.core.workflow.ports", "TaskVariableRepository"): (
        f"{SQLITE}.task_repo",
        "SqliteTaskVariableRepository",
    ),
}


def _declared_repository_protocols() -> set[tuple[str, str]]:
    """core 下所有 *Repository Protocol 的 (模块, 类名)。"""
    found: set[tuple[str, str]] = set()
    for path in sorted(CORE.glob("*/ports.py")):
        module = f"mailbus.core.{path.parent.name}.ports"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Repository"):
                found.add((module, node.name))
    return found


def test_every_repository_protocol_has_impl() -> None:
    missing = _declared_repository_protocols() - set(CONTRACTS)
    assert not missing, "以下协议缺少 SQLite 实现登记：" + ", ".join(
        f"{mod}.{name}" for mod, name in sorted(missing)
    )


def test_impl_covers_all_protocol_members() -> None:
    problems: list[str] = []
    for (proto_mod, proto_name), (impl_mod, impl_name) in CONTRACTS.items():
        proto = getattr(import_module(proto_mod), proto_name)
        impl = getattr(import_module(impl_mod), impl_name)
        for member, value in vars(proto).items():
            if member.startswith("_") or not callable(value):
                continue
            if not hasattr(impl, member):
                problems.append(f"{impl_name} 缺少 {proto_name}.{member}")
    assert not problems, "实现与协议不一致：\n" + "\n".join(problems)
