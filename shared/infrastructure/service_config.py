from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar

import yaml
from pydantic import BaseModel
from v2.nacos import (
    ClientConfigBuilder,
    ConfigParam,
    GRPCConfig,
    NacosConfigService,
    NacosNamingService,
    RegisterInstanceParam,
)

from shared.configuration.connection_settings import NacosConnectionSettings, ServiceConnectionSettings
from shared.configuration.service_settings import ServiceIdentitySettings
from shared.infrastructure.snowflake_id_generator import snowflake_ids

SettingsT = TypeVar("SettingsT", bound=BaseModel)


# 定义配置提供器接口
class ConfigProvider(ABC):
    # 建立连接
    @abstractmethod
    async def connect(self) -> None: ...

    # 获取数据
    @abstractmethod
    async def get(self, key: str) -> dict: ...

    # 监听配置变化
    @abstractmethod
    async def watch(self, key: str, callback) -> None: ...

    # 注册组件
    @abstractmethod
    async def register(self, service_name: str, instance_id: str, addr: str) -> None: ...

    # 关闭资源
    @abstractmethod
    async def close(self) -> None: ...


# 从Nacos加载和监听配置
class NacosConfigProvider(ConfigProvider):
    # 初始化当前实例
    def __init__(self) -> None:
        self._settings = NacosConnectionSettings()
        self._config_client = None
        self._naming_client = None

    # 建立连接
    async def connect(self) -> None:
        builder = (
            ClientConfigBuilder()
            .server_address(self._settings.addrs)
            .grpc_config(GRPCConfig(grpc_timeout=self._settings.grpc_timeout_ms))
        )
        if self._settings.user is not None:
            builder = builder.username(self._settings.user)
        if self._settings.password is not None:
            builder = builder.password(self._settings.password)
        if self._settings.namespace is not None:
            builder = builder.namespace_id(self._settings.namespace)
        self._client_config = builder.build()
        self._config_client = await NacosConfigService.create_config_service(self._client_config)

    # 获取数据
    async def get(self, key: str) -> dict:
        if self._config_client is None:
            raise RuntimeError("NacosConfigProvider 未 connect")
        content = await self._config_client.get_config(ConfigParam(data_id=key, group=self._settings.group))
        if not content:
            raise KeyError(f"Nacos 缺少配置: {key}")
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise TypeError(f"Nacos 配置 {key} 必须是对象")
        return parsed

    # 监听配置变化
    async def watch(self, key: str, callback) -> None:

        # 监听配置变化事件
        async def _listener(tenant: str, group: str, data_id: str, content: str) -> None:
            if not content:
                raise KeyError(f"Nacos 配置 {data_id} 不能为空")
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                raise TypeError(f"Nacos 配置 {data_id} 必须是对象")
            await callback(data_id, parsed)

        await self._config_client.add_listener(key, self._settings.group, _listener)

    # 注册组件
    async def register(self, service_name: str, instance_id: str, addr: str) -> None:
        if self._naming_client is None:
            self._naming_client = await NacosNamingService.create_naming_service(self._client_config)
        ip, _, port = addr.rpartition(":")
        await self._naming_client.register_instance(
            RegisterInstanceParam(
                service_name=service_name,
                group_name=self._settings.group,
                ip=ip,
                port=int(port),
                metadata={"instance_id": instance_id},
            )
        )

    # 关闭资源
    async def close(self) -> None:
        if self._config_client is not None:
            await self._config_client.shutdown()
            self._config_client = None
        if self._naming_client is not None:
            await self._naming_client.shutdown()
            self._naming_client = None


# 表示服务配置数据
@dataclass
class ServiceConfig:
    service_name: str
    nacos: ConfigProvider
    bus_url: str
    bus_token: str | None
    instance_addr: str
    instance_id: str = field(default_factory=lambda: str(snowflake_ids().next_id()))
    _section: dict = field(init=False)
    _section_key: str = field(init=False)
    _watching: bool = field(init=False, default=False)

    # 加载数据
    @classmethod
    async def load(cls, service_name: str) -> "ServiceConfig":
        provider = NacosConfigProvider()
        await provider.connect()
        connection = ServiceConnectionSettings()
        section = None
        for attempt in range(connection.config_retry_count):
            try:
                section = await provider.get(f"service.{service_name}")
                break
            except KeyError:
                if attempt + 1 == connection.config_retry_count:
                    raise
                await asyncio.sleep(connection.config_retry_interval_sec)
        if section is None:
            raise RuntimeError(f"配置重试次数必须大于零: service.{service_name}")
        identity = ServiceIdentitySettings.model_validate(section)
        cfg = cls(
            service_name=service_name,
            nacos=provider,
            bus_url=connection.bus_url,
            bus_token=connection.bus_token,
            instance_addr=identity.instance_addr,
        )
        cfg._section = section
        cfg._section_key = f"service.{service_name}"
        await cfg._subscribe()
        return cfg

    # 订阅消息
    async def _subscribe(self) -> None:
        if self._watching:
            return
        self._watching = True

        # 处理配置变更
        async def _on_change(data_id: str, parsed: dict) -> None:
            if not parsed:
                raise RuntimeError(f"Nacos 配置 {data_id} 不能为空")
            self._section = parsed

        await self.nacos.watch(self._section_key, _on_change)

    # 读取配置段
    async def section(self, settings_type: type[SettingsT]) -> SettingsT:
        return settings_type.model_validate(self._section)

    # 加载导演配置
    async def director(self, session_id: str, settings_type: type[SettingsT]) -> SettingsT:
        key = f"director.{session_id}"
        section = await self.nacos.get(key)
        if not section:
            raise RuntimeError(f"Nacos 缺少配置: {key}")
        return settings_type.model_validate(section)
