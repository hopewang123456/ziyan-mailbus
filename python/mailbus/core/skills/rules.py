"""技能包的纯函数状态转移。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.shared.events import DomainEvent
from mailbus.core.skills.errors import SkillSourceInvalidError
from mailbus.core.skills.models import SkillBinding, SkillPackage, SkillProbe
from mailbus.core.skills.values import (
    DEFAULT_ENTRY,
    MAX_NAME_LENGTH,
    MAX_URI_LENGTH,
    PATCHABLE_FIELDS,
    SOURCE_FIELDS,
    SkillSourceType,
    SkillTargetType,
)


def _event(kind: str, **payload: object) -> DomainEvent:
    return DomainEvent(kind=kind, payload=dict(payload))


def _text(value: object, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise InvalidStateError(f"{label}必须是字符串")
    text = value.strip()
    if not text:
        raise InvalidStateError(f"{label}不能为空")
    if len(text) > limit:
        raise InvalidStateError(f"{label}不能超过 {limit} 个字符")
    return text


def _note(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidStateError("备注必须是字符串")
    return value.strip()[:MAX_URI_LENGTH]


def _source_type(value: object) -> SkillSourceType:
    try:
        return SkillSourceType(value)
    except ValueError as exc:
        raise SkillSourceInvalidError("来源类型只支持 local 或 http") from exc


def _source_uri(value: object, source_type: SkillSourceType) -> str:
    uri = _text(value, "来源地址", MAX_URI_LENGTH)
    if source_type is SkillSourceType.HTTP and not uri.startswith(
        ("http://", "https://")
    ):
        raise SkillSourceInvalidError("http 来源必须是 http(s) 地址")
    return uri


def create_package(
    package_id: str,
    *,
    name: str,
    source_type: SkillSourceType,
    source_uri: str,
    entry: str = DEFAULT_ENTRY,
    note: str = "",
    now: datetime,
) -> tuple[SkillPackage, tuple[DomainEvent, ...]]:
    package = SkillPackage(
        package_id=package_id,
        name=_text(name, "技能包名称", MAX_NAME_LENGTH),
        source_type=_source_type(source_type.value),
        source_uri=_source_uri(source_uri, source_type),
        entry=_text(entry or DEFAULT_ENTRY, "入口文件", MAX_NAME_LENGTH),
        note=_note(note),
        created_at=now,
        updated_at=now,
    )
    event = _event(
        "skills.package_created",
        package_id=package.package_id,
        name=package.name,
        at=now.isoformat(),
    )
    return package, (event,)


def update_package(
    package: SkillPackage, changes: dict[str, object], now: datetime
) -> tuple[SkillPackage, tuple[DomainEvent, ...]]:
    unknown = set(changes) - PATCHABLE_FIELDS
    if unknown:
        raise InvalidStateError(f"不允许修改字段：{', '.join(sorted(unknown))}")
    values: dict[str, object] = {}
    source_changed = bool(SOURCE_FIELDS & set(changes))
    source_type = package.source_type
    if "source_type" in changes:
        source_type = _source_type(changes["source_type"])
        values["source_type"] = source_type
    if "name" in changes:
        values["name"] = _text(changes["name"], "技能包名称", MAX_NAME_LENGTH)
    if "source_uri" in changes:
        values["source_uri"] = _source_uri(changes["source_uri"], source_type)
    if "entry" in changes:
        values["entry"] = _text(changes["entry"], "入口文件", MAX_NAME_LENGTH)
    if "note" in changes:
        values["note"] = _note(changes["note"])
    if "enabled" in changes:
        values["enabled"] = bool(changes["enabled"])
    if all(getattr(package, key) == value for key, value in values.items()):
        return package, ()
    if source_changed:
        values.update(version="", last_error=None, last_checked_at=None)
    updated = replace(package, updated_at=now, **values)
    event = _event(
        "skills.package_updated",
        package_id=package.package_id,
        fields=sorted(values),
        at=now.isoformat(),
    )
    return updated, (event,)


def apply_probe(
    package: SkillPackage, probe: SkillProbe, now: datetime
) -> tuple[SkillPackage, tuple[DomainEvent, ...]]:
    """可达时更新版本，不可达时只记录错误；两种情况都刷新检查时间。"""
    if probe.reachable:
        updated = replace(
            package,
            version=probe.version or package.version,
            last_error=None,
            last_checked_at=now,
            updated_at=now,
        )
        kind = "skills.refresh_succeeded"
    else:
        updated = replace(
            package,
            last_error=probe.error or "来源不可达",
            last_checked_at=now,
            updated_at=now,
        )
        kind = "skills.refresh_failed"
    event = _event(
        kind,
        package_id=package.package_id,
        version=updated.version,
        error=updated.last_error or "",
        at=now.isoformat(),
    )
    return updated, (event,)


def make_binding(
    package_id: str,
    target_type: SkillTargetType,
    target_id: str,
    enabled: bool,
    now: datetime,
) -> tuple[SkillBinding, tuple[DomainEvent, ...]]:
    binding = SkillBinding(
        package_id=package_id,
        target_type=_target_type(target_type),
        target_id=_text(target_id, "绑定目标", MAX_NAME_LENGTH),
        enabled=enabled,
        created_at=now,
    )
    event = _event(
        "skills.binding_changed",
        package_id=package_id,
        target_type=binding.target_type.value,
        target_id=binding.target_id,
        enabled=enabled,
        at=now.isoformat(),
    )
    return binding, (event,)


def delete_package(package: SkillPackage, now: datetime) -> tuple[DomainEvent, ...]:
    return (
        _event(
            "skills.package_deleted",
            package_id=package.package_id,
            at=now.isoformat(),
        ),
    )


def _target_type(value: object) -> SkillTargetType:
    try:
        return SkillTargetType(value)
    except ValueError as exc:
        raise InvalidStateError("绑定目标只支持 agent 或 employee") from exc
