"""技能包的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceTypeIn = Literal["local", "http"]
TargetTypeIn = Literal["agent", "employee"]


class SkillPackageIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    source_type: SourceTypeIn
    source_uri: str = Field(min_length=1, max_length=512)
    entry: str = Field(default="SKILL.md", min_length=1, max_length=64)
    note: str = Field(default="", max_length=512)


class SkillPackageUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    source_type: SourceTypeIn | None = None
    source_uri: str | None = Field(default=None, min_length=1, max_length=512)
    entry: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


class SkillBindingIn(BaseModel):
    target_type: TargetTypeIn
    target_id: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class SkillBindingOut(BaseModel):
    target_type: str
    target_id: str
    enabled: bool


class SkillPackageOut(BaseModel):
    package_id: str
    name: str
    source_type: str
    source_uri: str
    entry: str
    version: str
    enabled: bool
    note: str
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    bindings: list[SkillBindingOut]


class EffectiveSkillOut(BaseModel):
    package_id: str
    name: str
    source_type: str
    source_uri: str
    entry: str
    version: str
    enabled: bool
    note: str
    origin: str
