"""对象装配：连接、UoW、派发器、时钟与 id 生成。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import closing
from datetime import timedelta

from mailbus.adapters.persistence.layout_seed import JsonLayoutSeed
from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.maintenance import (
    SqliteMaintenance,
    cutoff_from,
)
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.persistence.sqlite.uow import SqliteUnitOfWork
from mailbus.adapters.system.clock import SystemClock
from mailbus.adapters.system.concurrency import StreamGate
from mailbus.adapters.system.ids import UuidGenerator
from mailbus.adapters.system.metrics_manifest import MetricsManifest
from mailbus.adapters.system.rate_limit import RateLimiter
from mailbus.adapters.system.settings_store import JsonSettingsStore
from mailbus.adapters.system.skill_source import SkillSource
from mailbus.adapters.transport.a2a import A2aTransport
from mailbus.adapters.transport.collab_bus import InProcessEventBus
from mailbus.adapters.transport.file_bus import FileBusTransport
from mailbus.adapters.transport.file_bus_inbox import FileBusInbox
from mailbus.adapters.transport.mcp_pull import McpPullTransport
from mailbus.adapters.transport.routing import RoutingTransport
from mailbus.application.agents.directory import AgentDirectory
from mailbus.core.identity.values import EmployeeStatus
from mailbus.application.agents.service import AgentService
from mailbus.application.approval.service import ApprovalService
from mailbus.application.collab.messages import CollabMessageService
from mailbus.application.collab.pairs import PairService
from mailbus.application.collab.screens import ScreenService
from mailbus.application.dispatch.dispatcher import Dispatcher
from mailbus.application.identity.facade import IdentityServices
from mailbus.application.messaging.ingress import FileBusIngress
from mailbus.application.messaging.service import MessagingService
from mailbus.application.metrics.service import MetricsService
from mailbus.application.org.service import OrgService
from mailbus.application.queries.audit import AuditQuery
from mailbus.application.queries.layout import LayoutQuery
from mailbus.application.queries.log import LogQuery
from mailbus.application.queries.overview import OverviewQuery
from mailbus.application.settings.service import IntegrationService
from mailbus.application.skills.effective import SkillEffectiveQuery
from mailbus.application.skills.service import SkillService
from mailbus.application.workflow.service import WorkflowService
from mailbus.application.workflow.tasks import TaskService
from mailbus.bootstrap.settings import Settings

logger = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.clock = SystemClock()
        self.ids = UuidGenerator()
        self.layout_seed = JsonLayoutSeed(settings.layout_path)
        self.file_bus = FileBusTransport(settings.file_bus_dir)
        self.mcp_pull = McpPullTransport(settings.mcp_dir)
        self.a2a = A2aTransport(self._endpoint_of)
        self.transport = RoutingTransport(
            {"file_bus": self.file_bus, "mcp": self.mcp_pull, "a2a": self.a2a}
        )
        self.file_bus_inbox = FileBusInbox(settings.file_bus_dir)
        self.stream_gate = StreamGate(settings.sse_max_streams)
        self.public_register_limiter = RateLimiter(max_events=10, window_sec=60.0)
        self.public_apply_limiter = RateLimiter(max_events=5, window_sec=60.0)
        self.public_bootstrap_limiter = RateLimiter(max_events=5, window_sec=60.0)
        self._build_domain_services()
        self.schema_version = 0
        self._stop: asyncio.Event | None = None
        self._dispatcher_task: asyncio.Task[None] | None = None
        self._ingress_task: asyncio.Task[None] | None = None
        self._reaper_task: asyncio.Task[None] | None = None
        self._maintenance_task: asyncio.Task[None] | None = None

    def _build_domain_services(self) -> None:
        """装配领域服务；依赖方向保持单向：组织 → 身份 → 任务 → 观测。"""
        self.org = OrgService(self.uow, self.clock, self.ids, self.layout_seed)
        self.agent_directory = AgentDirectory(self.uow)
        self.agents = AgentService(self.uow, self.clock, self.ids)
        self.identity = IdentityServices.create(
            self.uow,
            self.clock,
            self.ids,
            self.org,
            self.layout_seed,
            self.agent_directory,
        )
        self.workflows = WorkflowService(self.uow, self.clock, self.ids)
        self.messages = MessagingService(self.uow, self.clock, self.ids)
        self.collab_events = InProcessEventBus(self.stream_gate)
        self.tasks = TaskService(
            self.uow, self.clock, self.ids, self.collab_events, self.identity.staff.seat_of
        )
        self.approvals = ApprovalService(self.uow, self.clock, self.ids)
        self.skills = SkillService(self.uow, self.clock, self.ids, SkillSource())
        self.skill_effective = SkillEffectiveQuery(self.uow)
        self.file_bus_ingress = FileBusIngress(
            self.messages, self.identity.sessions.resolve, self.file_bus_inbox
        )
        self.overview = OverviewQuery(self.uow, self.clock)
        manifest = MetricsManifest(self.settings.metrics_manifest_path)
        self.metrics = MetricsService(
            self.uow, self.clock, self.ids, manifest, self.overview
        )
        self.audit = AuditQuery(self.uow, self.metrics)
        self.integrations = IntegrationService(JsonSettingsStore(self.settings.settings_store_path))
        self.log = LogQuery(self.uow)
        self.screens = ScreenService(
            self.uow, self.clock, self.ids, self.collab_events,
            self.settings.public_screen_limit,
        )
        self.pairs = PairService(self.uow, self.clock, self.ids, self.collab_events)
        self.collab_messages = CollabMessageService(
            self.messages, self.uow, self.collab_events
        )
        self.layout = LayoutQuery(
            self.uow,
            self.layout_seed,
            self.identity.staff,
            self.tasks,
            self.agent_directory,
            self.pairs,
        )

    def uow(self) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(lambda: connect(self.settings.db_path), self.clock)

    def _endpoint_of(self, employee_id: str) -> str | None:
        """A2A 出站只投递到「在勤且端点已审核」的员工，防止自报端点被滥用。"""
        with self.uow() as uow:
            employee = uow.employees.get(employee_id)
        if employee is None or not employee.endpoint_approved:
            return None
        if employee.status not in (EmployeeStatus.ACTIVE, EmployeeStatus.OFFLINE):
            return None
        return employee.endpoint

    async def start(self) -> None:
        with closing(connect(self.settings.db_path)) as conn:
            self.schema_version = apply_migrations(conn)
        dispatcher = Dispatcher(
            self.uow,
            self.transport,
            interval_sec=self.settings.dispatch_interval_sec,
            batch=self.settings.dispatch_batch,
            sweeper=self.approvals.sweep_expired,
            on_result=self.messages.record_delivery,
            max_attempts=self.settings.dispatch_max_attempts,
        )
        self._stop = asyncio.Event()
        self._dispatcher_task = asyncio.create_task(
            dispatcher.run(self._stop), name="mailbus-dispatcher"
        )
        self._ingress_task = asyncio.create_task(
            self.file_bus_ingress.run(
                self._stop, self.settings.dispatch_interval_sec
            ),
            name="mailbus-file-bus",
        )
        self._reaper_task = asyncio.create_task(
            self._reap_loop(), name="mailbus-heartbeat-reaper"
        )
        self._maintenance_task = asyncio.create_task(
            self._prune_loop(), name="mailbus-retention-pruner"
        )

    async def _reap_loop(self) -> None:
        """心跳超时巡检：停止心跳的 active 员工自动转 offline。"""
        assert self._stop is not None
        while not self._stop.is_set():
            try:
                cutoff = self.clock.now() - timedelta(
                    seconds=self.settings.heartbeat_timeout_sec
                )
                await asyncio.to_thread(self.identity.staff.mark_stale_offline, cutoff)
            except Exception:  # 后台巡检失败不应拖垮服务，但要留痕
                logger.exception("心跳超时巡检失败")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.heartbeat_sweep_interval_sec
                )
            except asyncio.TimeoutError:
                continue

    def _prune_once(self, cutoff) -> int:
        with closing(connect(self.settings.db_path)) as conn:
            return SqliteMaintenance(conn).prune(cutoff)

    async def _prune_loop(self) -> None:
        """保留期清理：已派发事件、审计流水、幂等键与失效会话。"""
        assert self._stop is not None
        interval = self.settings.maintenance_interval_sec
        while not self._stop.is_set():
            try:
                cutoff = cutoff_from(self.clock.now(), self.settings.retention_days)
                removed = await asyncio.to_thread(self._prune_once, cutoff)
                if removed:
                    logger.info("保留期清理删除 %d 行", removed)
            except Exception:  # 后台清理失败不应拖垮服务，但要留痕
                logger.exception("保留期清理失败")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._maintenance_task is not None:
            await self._maintenance_task
            self._maintenance_task = None
        if self._reaper_task is not None:
            await self._reaper_task
            self._reaper_task = None
        if self._dispatcher_task is not None:
            await self._dispatcher_task
            self._dispatcher_task = None
        if self._ingress_task is not None:
            await self._ingress_task
            self._ingress_task = None
