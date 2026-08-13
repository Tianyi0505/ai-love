
from __future__ import annotations

import asyncio
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import yaml
from v2.nacos import (
    ClientConfigBuilder,
    ConfigParam,
    GRPCConfig,
    NacosConfigService,
    NacosNamingService,
    RegisterInstanceParam,
)

from shared.infrastructure.runtime_config import required_setting


class ConfigProvider(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> dict: ...

    @abstractmethod
    async def watch(self, key: str, callback) -> None: ...

    @abstractmethod
    async def register(self, service_name: str, instance_id: str, addr: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class NacosConfigProvider(ConfigProvider):

    def __init__(
        self,
        server_addrs: str | None = None,
        namespace: str = "",
        group: str = "DEFAULT_GROUP",
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._server_addrs = required_setting(server_addrs, "AILOVE_NACOS_ADDRS")
        self._namespace = namespace or os.environ.get("AILOVE_NACOS_NAMESPACE", "")
        self._group = group
        self._username = username or os.environ.get("AILOVE_NACOS_USER", "")
        self._password = password or os.environ.get("AILOVE_NACOS_PASSWORD", "")
        self._config_client = None
        self._naming_client = None

    async def connect(self) -> None:
        builder = (
            ClientConfigBuilder()
            .server_address(self._server_addrs)
            .username(self._username)
            .password(self._password)
            .grpc_config(GRPCConfig(grpc_timeout=5000))
        )
        if self._namespace:
            builder = builder.namespace_id(self._namespace)
        self._client_config = builder.build()
        self._config_client = await NacosConfigService.create_config_service(self._client_config)

    async def get(self, key: str) -> dict:
        if self._config_client is None:
            raise RuntimeError("NacosConfigProvider 未 connect")
        content = await self._config_client.get_config(ConfigParam(data_id=key, group=self._group))
        if not content:
            return {}
        parsed = yaml.safe_load(content)
        return parsed if isinstance(parsed, dict) else {}

    async def watch(self, key: str, callback) -> None:

        async def _listener(tenant: str, group: str, data_id: str, content: str) -> None:
            parsed = yaml.safe_load(content) if content else {}
            await callback(data_id, parsed if isinstance(parsed, dict) else {})

        await self._config_client.add_listener(key, self._group, _listener)

    async def register(self, service_name: str, instance_id: str, addr: str) -> None:
        if self._naming_client is None:
            self._naming_client = await NacosNamingService.create_naming_service(self._client_config)
        ip, _, port = addr.rpartition(":")
        await self._naming_client.register_instance(
            RegisterInstanceParam(
                service_name=service_name,
                group_name=self._group,
                ip=ip,
                port=int(port),
                weight=1.0,
                ephemeral=True,
                metadata={"instance_id": instance_id},
            )
        )

    async def close(self) -> None:
        if self._config_client is not None:
            await self._config_client.shutdown()
            self._config_client = None
        if self._naming_client is not None:
            await self._naming_client.shutdown()
            self._naming_client = None


@dataclass
class ServiceConfig:

    service_name: str
    nacos: ConfigProvider | None = None
    bus_url: str = ""
    bus_token: str = ""
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    instance_addr: str = "127.0.0.1:0"

    @classmethod
    async def load(cls, service_name: str) -> "ServiceConfig":
        provider = NacosConfigProvider()
        await provider.connect()
        cfg = cls(service_name=service_name, nacos=provider)
        section = {}
        for _ in range(5):
            section = await provider.get(f"service.{service_name}")
            if section:
                break
            await asyncio.sleep(2)
        cfg.bus_url = required_setting(section.get("bus_url") or cfg.bus_url, "AILOVE_BUS_URL")
        cfg.instance_addr = section.get("instance_addr", cfg.instance_addr)
        cfg._section = section
        cfg._section_key = f"service.{service_name}"
        await cfg._subscribe()
        return cfg

    def __post_init__(self) -> None:
        self.bus_url = os.environ.get("AILOVE_BUS_URL", self.bus_url)
        self.bus_token = os.environ.get("AILOVE_BUS_TOKEN", self.bus_token)
        self._section: dict = {}
        self._section_key = ""

    async def _subscribe(self) -> None:
        if self.nacos is None or getattr(self, "_watching", False):
            return
        self._watching = True

        async def _on_change(data_id: str, parsed: dict) -> None:
            self._section = parsed or {}

        await self.nacos.watch(self._section_key, _on_change)

    async def section(self, key: str = "") -> dict:
        if self.nacos is None:
            return {}
        section = self._section
        if not key:
            return section
        return section.get(key, {})

    async def director(self, session_id: str) -> dict:
        if self.nacos is None:
            return {}
        return await self.nacos.get(f"director.{session_id}")
