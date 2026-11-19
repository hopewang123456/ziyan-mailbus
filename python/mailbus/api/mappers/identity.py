"""identity 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.identity import (
    ApplyIn,
    ApplyOut,
    BootstrapStatusOut,
    BootstrapStepOut,
    EmployeeOut,
    InviteIn,
    InviteOut,
    ModelConfigIn,
    ReviewIn,
    SessionOut,
    SuperAdminIn,
)
from mailbus.application.identity.dto import (
    ApplyCommand,
    BootstrapStatusView,
    EmployeeView,
    InviteCommand,
    InviteView,
    ModelConfigCommand,
    ReviewCommand,
    SessionResult,
    SuperAdminCommand,
    make_apply_command,
    make_invite_command,
    make_model_config_command,
    make_review_command,
    make_super_admin_command,
)


def to_employee_out(view: EmployeeView) -> EmployeeOut:
    return EmployeeOut(
        employee_id=view.employee_id,
        display_name=view.display_name,
        account_type=view.account_type,
        status=view.status,
        team_id=view.team_id,
        position_id=view.position_id,
        seat_id=view.seat_id,
        agent_id=view.agent_id,
        agent_name=view.agent_name,
        agent_framework=view.agent_framework,
        capabilities=list(view.capabilities),
        data_scope=view.data_scope,
        file_scope=list(view.file_scope),
        endpoint=view.endpoint,
        endpoint_approved=view.endpoint_approved,
        last_heartbeat=view.last_heartbeat,
    )


def to_session_out(result: SessionResult) -> SessionOut:
    return SessionOut(employee=to_employee_out(result.employee), token=result.token)


def to_apply_out(result: ApplyResult) -> ApplyOut:
    return ApplyOut(employee=to_employee_out(result.employee), token=result.token)


def to_bootstrap_out(view: BootstrapStatusView) -> BootstrapStatusOut:
    return BootstrapStatusOut(
        steps=[
            BootstrapStepOut(step=step.step, done=step.done, skippable=step.skippable)
            for step in view.steps
        ],
        completed=view.completed,
    )


def to_invite_out(view: InviteView) -> InviteOut:
    return InviteOut(
        invite_code=view.invite_code,
        account_type=view.account_type,
        team_id=view.team_id,
        position_id=view.position_id,
        data_scope=view.data_scope,
        capabilities=list(view.capabilities),
        expires_at=view.expires_at,
    )


def apply_command(payload: ApplyIn) -> ApplyCommand:
    return make_apply_command(
        display_name=payload.display_name,
        account_type=payload.account_type,
        invite_code=payload.invite_code,
        endpoint=payload.endpoint,
        seat_id=payload.seat_id,
        agent_id=payload.agent_id,
    )


def review_command(payload: ReviewIn) -> ReviewCommand:
    return make_review_command(approved=payload.approved, note=payload.note)


def invite_command(payload: InviteIn) -> InviteCommand:
    return make_invite_command(
        account_type=payload.account_type,
        team_id=payload.team_id,
        position_id=payload.position_id,
        capabilities=tuple(payload.capabilities),
        data_scope=payload.data_scope,
        expires_in_hours=payload.expires_in_hours,
    )


def super_admin_command(payload: SuperAdminIn) -> SuperAdminCommand:
    return make_super_admin_command(
        display_name=payload.display_name, employee_id=payload.employee_id
    )


def model_config_command(payload: ModelConfigIn) -> ModelConfigCommand:
    return make_model_config_command(
        provider=payload.provider, model=payload.model, api_base=payload.api_base
    )
