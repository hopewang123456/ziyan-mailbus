"""任务产物上传用例：权限校验、磁盘落盘与审计记录。

为控制 TaskEngine 体量，本模块承载产物写入流程；引擎只做薄委托。
"""
from __future__ import annotations

from pathlib import Path

from mailbus.application.task.dto import ArtifactView, artifact_view
from mailbus.application.task.reader import TaskReader
from mailbus.core.shared.errors import (
    InvalidStateError,
    PermissionDeniedError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow.models import TaskArtifact


class ArtifactUploader:
    def __init__(self, uow_factory, clock: Clock, ids: IdGenerator,
                 reader: TaskReader, artifacts_dir, ensure_open, publish) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._reader = reader
        self._artifacts_dir = artifacts_dir
        self._ensure_open = ensure_open
        self._publish = publish

    def upload(self, actor, task_id: str, node_id: str, file_name: str,
               file_bytes: bytes, description: str | None) -> ArtifactView:
        if not file_bytes:
            raise UnprocessableError("产物文件为空")
        if self._artifacts_dir is None:
            raise UnprocessableError("产物存储未配置")
        now = self._clock.now()
        with self._uow() as uow:
            task = self._reader.load(uow, task_id)
            runs = uow.runs.list_by_task(task_id)
            self._reader.ensure_visible(actor, uow, task, runs)
            self._ensure_open(task)
            if not any(node.node_id == node_id for node in uow.tasks.nodes(task_id)):
                raise UnprocessableError("节点不属于该任务")
            node_runs = [run for run in runs if run.node_id == node_id]
            if not node_runs:
                raise InvalidStateError("节点尚未派发执行实例")
            run = max(node_runs, key=lambda item: item.attempt_no)
            if (Capability.ALL not in actor.capabilities
                    and actor.employee_id not in (task.owner_id, task.created_by)
                    and run.assigned_employee_id not in (None, actor.employee_id)):
                raise PermissionDeniedError("只有当前执行人可以上传产物")
            artifact_id = self._ids.new("artifact")
            safe_name = Path(file_name).name or "artifact"
            dest = Path(self._artifacts_dir) / task_id / f"{artifact_id}_{safe_name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(file_bytes)
            artifact = TaskArtifact(
                artifact_id=artifact_id, task_id=task_id, node_id=node_id,
                run_id=run.run_id, file_path=str(dest), file_name=safe_name,
                artifact_type=None, description=description or None,
                created_by=actor.employee_id, created_at=now, version=1,
            )
            uow.artifacts.add(artifact)
            uow.audit.record(
                actor.employee_id, "task.artifact_upload", f"task:{task_id}",
                {"task_id": task_id, "node_id": node_id, "run_id": run.run_id,
                 "artifact_id": artifact_id, "file_name": safe_name},
            )
            uow.commit()
        self._publish(task_id)
        return artifact_view(artifact)
