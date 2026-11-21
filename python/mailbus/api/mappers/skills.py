"""技能包协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.skills import (
    EffectiveSkillOut,
    SkillBindingOut,
    SkillBindingIn,
    SkillPackageIn,
    SkillPackageOut,
    SkillPackageUpdateIn,
)
from mailbus.application.skills.dto import (
    EffectiveSkillView,
    SkillBindingCommand,
    SkillBindingView,
    SkillPackageCommand,
    SkillPackageView,
    SkillUpdateCommand,
    make_binding_command,
    make_package_command,
    make_update_command,
)


def to_package_out(
    view: SkillPackageView, *, include_sensitive: bool = True
) -> SkillPackageOut:
    return SkillPackageOut(
        package_id=view.package_id,
        name=view.name,
        source_type=view.source_type,
        source_uri=view.source_uri if include_sensitive else None,
        entry=view.entry if include_sensitive else None,
        version=view.version,
        enabled=view.enabled,
        note=view.note,
        last_checked_at=view.last_checked_at,
        last_error=view.last_error,
        created_at=view.created_at,
        updated_at=view.updated_at,
        bindings=[_binding(item) for item in view.bindings],
    )


def _binding(view: SkillBindingView) -> SkillBindingOut:
    return SkillBindingOut(
        target_type=view.target_type,
        target_id=view.target_id,
        enabled=view.enabled,
    )


def to_effective_out(
    view: EffectiveSkillView, *, include_sensitive: bool = True
) -> EffectiveSkillOut:
    return EffectiveSkillOut(
        package_id=view.package_id,
        name=view.name,
        source_type=view.source_type,
        source_uri=view.source_uri if include_sensitive else None,
        entry=view.entry if include_sensitive else None,
        version=view.version,
        enabled=view.enabled,
        note=view.note,
        origin=view.origin,
    )


def package_command(payload: SkillPackageIn) -> SkillPackageCommand:
    return make_package_command(
        name=payload.name,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
        entry=payload.entry,
        note=payload.note,
    )


def update_command(payload: SkillPackageUpdateIn) -> SkillUpdateCommand:
    return make_update_command(payload.model_dump(exclude_unset=True))


def binding_command(payload: SkillBindingIn) -> SkillBindingCommand:
    return make_binding_command(
        target_type=payload.target_type,
        target_id=payload.target_id,
        enabled=payload.enabled,
    )
