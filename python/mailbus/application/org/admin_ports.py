"""组织管理用例所需的聚合工作单元协议（仅静态约束，实现由 adapters 提供）。"""

from __future__ import annotations

from typing import Protocol

from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.org.ports import OrgUnitOfWork, RoleRepository


class OrgAdminUnitOfWork(IdentityUnitOfWork, OrgUnitOfWork, Protocol):
    roles: RoleRepository
