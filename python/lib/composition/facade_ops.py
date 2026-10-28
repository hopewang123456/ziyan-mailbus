"""Composition facades — ops / plane / runtime / locale domain (R2 split).

Target domain: adapters.ops.* + adapters.plane.* + adapters.runtime.* + adapters.locale.*
(doctor / clinic / heartbeat / alerts / scheduler / search / acceptance / locale catalogs).
"""
from __future__ import annotations

from typing import Any


def index_catalog(data_dir: str, agents: dict) -> Any:
    from lib.adapters.ops.catalog_search import index_catalog as _index

    return _index(data_dir, agents)


def search_catalog(data_dir: str, *, query_str: str = "", limit: int = 20) -> Any:
    from lib.adapters.ops.catalog_search import search_catalog as _search

    return _search(data_dir, query_str=query_str, limit=limit)


def search_all(
    data_dir: str,
    *,
    query_str: str = "",
    limit: int = 20,
    agents: dict | None = None,
) -> Any:
    from lib.adapters.ops.catalog_search import search_all as _search

    return _search(data_dir, query_str=query_str, limit=limit, agents=agents)


def scheduler_hub_factory():
    """SchedulerHub 工厂 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.scheduler.SchedulerHub`。
    """
    from lib.adapters.ops.scheduler import SchedulerHub

    return SchedulerHub


def run_connection_test(*args: Any, **kwargs: Any):
    """E1 三段式测试连接 — api/CLI 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.connection_test.run_connection_test`。
    """
    from lib.adapters.ops.connection_test import run_connection_test as _impl

    return _impl(*args, **kwargs)


def format_connection_text(*args: Any, **kwargs: Any):
    """E1 测试连接的 CLI 文本渲染 — composition 门面（分层约束）。"""
    from lib.adapters.ops.connection_test import format_connection_text as _impl

    return _impl(*args, **kwargs)


def push_alert(*args: Any, **kwargs: Any):
    """告警推送 — application 经此访问（分层约束）。

    实际实现见 `lib.adapters.ops.alerter.push_alert`。
    """
    from lib.adapters.ops.alerter import push_alert as _impl

    return _impl(*args, **kwargs)


def send_notification(*args: Any, **kwargs: Any):
    """M1 W1 外呼通知（desktop/webhook/smtp/file 四渠道分发）— application/api 经此访问（分层约束）。

    实际实现见 `lib.adapters.ops.notifier.send_notification`。
    """
    from lib.adapters.ops.notifier import send_notification as _impl

    return _impl(*args, **kwargs)


def acceptance_status(*args: Any, **kwargs: Any):
    """M1 W4 验收观察项对账（六项健康检查）— application/api/哨兵 经此访问（分层约束）。

    实际实现见 `lib.adapters.ops.acceptance.acceptance_status`。
    """
    from lib.adapters.ops.acceptance import acceptance_status as _impl

    return _impl(*args, **kwargs)


def format_acceptance_text(*args: Any, **kwargs: Any):
    """M1 W4 对账结果的人读渲染 — application 经此访问（分层约束）。"""
    from lib.adapters.ops.acceptance import format_acceptance_text as _impl

    return _impl(*args, **kwargs)


def probe_service(*args: Any, **kwargs: Any):
    """Service probe — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.service_registry.probe_service`。
    """
    from lib.adapters.ops.service_registry import probe_service as _impl

    return _impl(*args, **kwargs)


def load_heartbeat(*args: Any, **kwargs: Any):
    """Heartbeat status load — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.heartbeat.load_status`。
    """
    from lib.adapters.ops.heartbeat import load_status as _impl

    return _impl(*args, **kwargs)


def get_recent_alerts(*args: Any, **kwargs: Any):
    """Recent alerts — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.alerter.get_recent_alerts`。
    """
    from lib.adapters.ops.alerter import get_recent_alerts as _impl

    return _impl(*args, **kwargs)


def get_scheduler_status_sys(*args: Any, **kwargs: Any):
    """Scheduler status — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.scheduler.get_scheduler_status`。
    """
    from lib.adapters.ops.scheduler import get_scheduler_status as _impl

    return _impl(*args, **kwargs)


def running_in_mailbus_docker():
    """Platform runner in-docker — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.plane.platform_runner.running_in_mailbus_docker`。
    """
    from lib.adapters.plane.platform_runner import running_in_mailbus_docker as _impl

    return _impl()


def apply_instance_endpoint(*args: Any, **kwargs: Any):
    """Instance endpoint apply — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.runtime.cred_delivery.apply_instance_endpoint`。
    """
    from lib.adapters.runtime.cred_delivery import apply_instance_endpoint as _impl

    return _impl(*args, **kwargs)


def search(*args: Any, **kwargs: Any):
    """通用检索 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.search.search`。
    """
    from lib.adapters.ops.search import search as _impl

    return _impl(*args, **kwargs)


def list_external_tools_summary(*args: Any, **kwargs: Any):
    """外部工具汇总 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.catalog_search.list_external_tools_summary`。
    """
    from lib.adapters.ops.catalog_search import list_external_tools_summary as _impl

    return _impl(*args, **kwargs)


def is_online(*args: Any, **kwargs: Any):
    """心跳在线判定 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.heartbeat.is_online`。
    """
    from lib.adapters.ops.heartbeat import is_online as _impl

    return _impl(*args, **kwargs)


def list_clinic_tools(*args: Any, **kwargs: Any):
    """Clinic tool 清单 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.clinic_tools.list_clinic_tools`。
    """
    from lib.adapters.ops.clinic_tools import list_clinic_tools as _impl

    return _impl(*args, **kwargs)


def run_clinic_tool(*args: Any, **kwargs: Any):
    """Clinic tool 执行 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.clinic_tools.run_clinic_tool`。
    """
    from lib.adapters.ops.clinic_tools import run_clinic_tool as _impl

    return _impl(*args, **kwargs)


def run_doctor_checks(*args: Any, **kwargs: Any):
    """doctor 检查 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.doctor_checks.run_doctor_checks`。
    """
    from lib.adapters.ops.doctor_checks import run_doctor_checks as _impl

    return _impl(*args, **kwargs)


def format_doctor_text(*args: Any, **kwargs: Any):
    """doctor 报告人读渲染 — application 经此访问（分层约束）。"""
    from lib.adapters.ops.doctor_checks import format_doctor_text as _impl

    return _impl(*args, **kwargs)


def doctor_exit_code(*args: Any, **kwargs: Any):
    """doctor 退出码（0 健康 / 非 0 有红灯）— application 经此访问（分层约束）。"""
    from lib.adapters.ops.doctor_checks import doctor_exit_code as _impl

    return _impl(*args, **kwargs)


# ── locale 域（adapters.locale.*）──────────────────────────────────────


def message_zh(*args: Any, **kwargs: Any):
    """错误码中文消息 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.message_zh`。
    """
    from lib.adapters.locale.errors_zh import message_zh as _impl

    return _impl(*args, **kwargs)


def zh_to_role_type(*args: Any, **kwargs: Any):
    """中文角色名 → role_type — application 经此访问（分层约束）。"""
    from lib.adapters.locale.role_labels import zh_to_role_type as _impl

    return _impl(*args, **kwargs)


def locale_catalog(*args: Any, **kwargs: Any):
    """locale catalog — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.locale_catalog`。
    """
    from lib.adapters.locale.errors_zh import locale_catalog as _impl

    return _impl(*args, **kwargs)


def stable_codes_covered(*args: Any, **kwargs: Any):
    """locale 稳定码覆盖 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.stable_codes_covered`。
    """
    from lib.adapters.locale.errors_zh import stable_codes_covered as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "index_catalog",
    "search_catalog",
    "search_all",
    "scheduler_hub_factory",
    "run_connection_test",
    "format_connection_text",
    "push_alert",
    "send_notification",
    "acceptance_status",
    "format_acceptance_text",
    "probe_service",
    "load_heartbeat",
    "get_recent_alerts",
    "get_scheduler_status_sys",
    "running_in_mailbus_docker",
    "apply_instance_endpoint",
    "search",
    "list_external_tools_summary",
    "is_online",
    "list_clinic_tools",
    "run_clinic_tool",
    "run_doctor_checks",
    "format_doctor_text",
    "doctor_exit_code",
    "message_zh",
    "zh_to_role_type",
    "locale_catalog",
    "stable_codes_covered",
    "metrics_query",
    "metrics_snapshot",
    "metrics_manifest",
    "metrics_rules",
    "metrics_rule_patch",
    "archive_inbox_backlog",
]


# ── Metrics 域（P2 B1-B3）──────────────────────────────────────────────


def metrics_query(*args: Any, **kwargs: Any):
    """统一指标查询（B2 协议）— api/前端大盘/AI 助手 经此访问。"""
    from lib.adapters.metrics.query import query as _impl

    return _impl(*args, **kwargs)


def metrics_snapshot(*args: Any, **kwargs: Any):
    """采集全部 point 指标并落时序 — scheduler 周期调用。"""
    from lib.adapters.metrics.query import snapshot as _impl

    return _impl(*args, **kwargs)


def metrics_manifest(*args: Any, **kwargs: Any):
    """指标清单（B1 双栈 SoT）— api/前端经此访问。"""
    from lib.adapters.metrics.manifest import load_manifest as _impl

    return _impl(*args, **kwargs)


def metrics_rules(*args: Any, **kwargs: Any):
    """告警规则清单（B5）— api 经此访问（分层约束）。"""
    from lib.adapters.metrics.rules import load_rules as _impl

    return _impl(*args, **kwargs)


def metrics_rule_patch(*args: Any, **kwargs: Any):
    """告警规则编辑（B5）— api 经此访问；ValueError 语义保留。"""
    from lib.adapters.metrics.rules import patch_rule as _impl

    return _impl(*args, **kwargs)


def archive_inbox_backlog(*args: Any, **kwargs: Any):
    """归档 agent 的已结算消息 — api 经此访问（分层约束）。

    实际实现见 `lib.application.ops.store_cleanup.archive_inbox_backlog`。
    """
    from lib.application.ops.store_cleanup import archive_inbox_backlog as _impl

    return _impl(*args, **kwargs)
