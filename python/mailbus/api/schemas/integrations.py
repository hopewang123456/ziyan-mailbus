"""集成与运行配置的对外模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntegrationItemOut(BaseModel):
    name: str
    kind: str
    description: str
    actions: list[str]


class IntegrationsOut(BaseModel):
    integrations: list[IntegrationItemOut]
    plugins: list[str]
    note: str


class PluginActionIn(BaseModel):
    action: str
    spec: str


class PluginActionOut(BaseModel):
    plugins: list[str]


class IntegrationInvokeIn(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class EnvEntryOut(BaseModel):
    key: str
    label: str
    value: str
    configured: bool


class EnvGroupsOut(BaseModel):
    groups: dict[str, list[EnvEntryOut]]


class EnvUpdateIn(BaseModel):
    vars: dict[str, str | None] = Field(default_factory=dict)


class ReloadOut(BaseModel):
    reloaded: bool
    plugins: list[str]
