from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .resources import ResourceScope

Identifier = str


class PluginError(RuntimeError):
    """An actionable control-plane failure, safe to expose to the administrator."""

    def __init__(self, message: str, code: str = "conflict") -> None:
        super().__init__(message)
        self.code = code


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")
    name: str
    description: str
    host: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    entrypoint: str = Field(pattern=r"^[a-zA-Z_][\w.]*:[a-zA-Z_]\w*$")
    category: str = "extension"
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    isolation: Literal["trusted-in-process"] = "trusted-in-process"


class PluginCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")
    plugin_id: str
    action: Literal["install", "enable", "disable", "restart", "remove"]
    expected_revision: int = Field(ge=0)
    stop_dependents: bool = False


class Capabilities(Protocol):
    def resolve(self, capability: str) -> Any: ...


@dataclass
class PluginContext:
    """Only explicit host ports and declared capabilities cross the plugin boundary."""

    manifest: PluginManifest
    resources: ResourceScope
    capabilities: Capabilities
    ports: Mapping[str, Any]
    config: Mapping[str, Any]
    _exports: dict[str, Any] = field(default_factory=dict)

    def require(self, capability: str) -> Any:
        if capability not in self.manifest.requires:
            raise PluginError(f"未声明能力依赖：{capability}")
        return self.capabilities.resolve(capability)

    def provide(self, capability: str, value: Any) -> None:
        if capability not in self.manifest.provides or capability in self._exports:
            raise PluginError(f"未声明或重复提供能力：{capability}")
        self._exports[capability] = value


class Plugin:
    """One current contract; no plugin version negotiation or compatibility shims."""

    async def initialize(self, context: PluginContext) -> None:
        self.context = context

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispose(self) -> None:
        pass
