"""邀请管理的应用层视图。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.identity.models import Invite


@dataclass(frozen=True, slots=True)
class AdminInviteView:
    invite_id: str
    account_type: str
    data_scope: str
    permissions: tuple[str, ...]
    team_id: str | None = None
    position_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    invite_code: str | None = None

    @classmethod
    def of(cls, invite: Invite, *, plaintext: bool = False) -> "AdminInviteView":
        return cls(
            invite_id=invite.invite_code,
            account_type=invite.account_type.value,
            data_scope=invite.data_scope.value,
            permissions=tuple(sorted(cap.value for cap in invite.permissions)),
            team_id=invite.team_id,
            position_id=invite.position_id,
            created_by=invite.created_by,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            consumed_at=invite.consumed_at,
            revoked_at=invite.revoked_at,
            invite_code=invite.invite_code if plaintext else None,
        )
