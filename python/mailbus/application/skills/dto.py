"""技能包用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.skills.models import SkillBinding, SkillPackage
from mailbus.core.skills.values import DEFAULT_ENTRY, SkillSourceType, SkillTargetType


@dataclass(frozen=True, slots=True)
class SkillPackageCommand:
    name: str
    source_type: SkillSourceType
    source_uri: str
    entry: str = DEFAULT_ENTRY
    note: str = ""


@dataclass(frozen=True, slots=True)
class SkillUpdateCommand:
    changes: dict[str, object]


@dataclass(frozen=True, slots=True)
class SkillBindingCommand:
    target_type: SkillTargetType
    target_id: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SkillBindingView:
    target_type: str
    target_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class SkillPackageView:
    package_id: str
    name: str
    source_type: str
    source_uri: str
    entry: str
    version: str
    enabled: bool
    note: str
    last_checked_at: datetime | None
    last_error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    bindings: tuple[SkillBindingView, ...] = ()

    @classmethod
    def of(
        cls, package: SkillPackage, bindings: tuple[SkillBindingView, ...] = ()
    ) -> "SkillPackageView":
        return cls(
            package_id=package.package_id,
            name=package.name,
            source_type=package.source_type.value,
            source_uri=package.source_uri,
            entry=package.entry,
            version=package.version,
            enabled=package.enabled,
            note=package.note,
            last_checked_at=package.last_checked_at,
            last_error=package.last_error,
            created_at=package.created_at,
            updated_at=package.updated_at,
            bindings=bindings,
        )


@dataclass(frozen=True, slots=True)
class EffectiveSkillView:
    package_id: str
    name: str
    source_type: str
    source_uri: str
    entry: str
    version: str
    enabled: bool
    note: str
    origin: str


def binding_view(binding: SkillBinding) -> SkillBindingView:
    return SkillBindingView(
        target_type=binding.target_type.value,
        target_id=binding.target_id,
        enabled=binding.enabled,
    )


def make_package_command(
    name: str,
    source_type: str,
    source_uri: str,
    entry: str = DEFAULT_ENTRY,
    note: str = "",
) -> SkillPackageCommand:
    return SkillPackageCommand(
        name=name,
        source_type=SkillSourceType(source_type),
        source_uri=source_uri,
        entry=entry,
        note=note,
    )


def make_update_command(changes: dict[str, object]) -> SkillUpdateCommand:
    return SkillUpdateCommand(changes=dict(changes))


def make_binding_command(
    target_type: str, target_id: str, enabled: bool = True
) -> SkillBindingCommand:
    return SkillBindingCommand(
        target_type=SkillTargetType(target_type),
        target_id=target_id,
        enabled=enabled,
    )
