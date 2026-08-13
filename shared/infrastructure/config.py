
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

from shared.infrastructure.runtime_config import ConfigKey, required_config, required_setting


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
        self._server_addrs = required_setting(None, ConfigKey.AILOVE_NACOS_ADDRS)
        self._grpc_timeout_ms = int(
            required_setting(None, ConfigKey.AILOVE_NACOS_GRPC_TIMEOUT_MS)
        )
        self._namespace = os.environ.get("AILOVE_NACOS_NAMESPACE", "")
        self._group = required_setting(None, ConfigKey.AILOVE_NACOS_GROUP)
        self._username = os.environ.get("AILOVE_NACOS_USER", "")
        self._password = os.environ.get("AILOVE_NACOS_PASSWORD", "")
        self._config_client = None
        self._naming_client = None

    # 建立连接
    async def connect(self) -> None:
        builder = (
            ClientConfigBuilder()
            .server_address(self._server_addrs)
            .username(self._username)
            .password(self._password)
            .grpc_config(GRPCConfig(grpc_timeout=self._grpc_timeout_ms))
        )
        if self._namespace:
            builder = builder.namespace_id(self._namespace)
        self._client_config = builder.build()
        self._config_client = await NacosConfigService.create_config_service(self._client_config)

    # 获取数据
    async def get(self, key: str) -> dict:
        if self._config_client is None:
            raise RuntimeError("NacosConfigProvider 未 connect")
        content = await self._config_client.get_config(ConfigParam(data_id=key, group=self._group))
        if not content:
            return {}
        parsed = yaml.safe_load(content)
        return parsed if isinstance(parsed, dict) else {}

    # 监听配置变化
    async def watch(self, key: str, callback) -> None:

        # 监听配置变化事件
        async def _listener(tenant: str, group: str, data_id: str, content: str) -> None:
            parsed = yaml.safe_load(content) if content else {}
            await callback(data_id, parsed if isinstance(parsed, dict) else {})

        await self._config_client.add_listener(key, self._group, _listener)

    # 注册组件
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
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    _section: dict = field(init=False, default_factory=dict)
    _section_key: str = field(init=False, default="")

    # 加载数据
    @classmethod
    async def load(cls, service_name: str) -> "ServiceConfig":
        provider = NacosConfigProvider()
        await provider.connect()
        section = {}
        retry_count = int(required_setting(None, ConfigKey.AILOVE_CONFIG_RETRY_COUNT))
        retry_interval = float(
            required_setting(None, ConfigKey.AILOVE_CONFIG_RETRY_INTERVAL_SEC)
        )
        for _ in range(retry_count):
            section = await provider.get(f"service.{service_name}")
            if section:
                break
            await asyncio.sleep(retry_interval)
        if not section:
            raise RuntimeError(f"Nacos 缺少配置: service.{service_name}")
        cfg = cls(
            service_name=service_name,
            nacos=provider,
            bus_url=required_setting(None, ConfigKey.AILOVE_BUS_URL),
            bus_token=os.environ.get("AILOVE_BUS_TOKEN"),
            instance_addr=str(
                required_config(section, "instance_addr", f"service.{service_name}.instance_addr")
            ),
        )
        cfg._section = section
        cfg._section_key = f"service.{service_name}"
        await cfg._subscribe()
        return cfg

    # 订阅消息
    async def _subscribe(self) -> None:
        if getattr(self, "_watching", False):
            return
        self._watching = True

        # 处理配置变更
        async def _on_change(data_id: str, parsed: dict) -> None:
            if not parsed:
                raise RuntimeError(f"Nacos 配置 {data_id} 不能为空")
            self._section = parsed

        await self.nacos.watch(self._section_key, _on_change)

    # 读取配置段
    async def section(self, key: str = "") -> dict:
        section = self._section
        if not key:
            return section
        value = required_config(section, key, f"{self._section_key}.{key}")
        if not isinstance(value, dict):
            raise RuntimeError(f"{self._section_key}.{key} 必须是对象")
        return value

    # 加载导演配置
    async def director(self, session_id: str) -> dict:
        key = f"director.{session_id}"
        section = await self.nacos.get(key)
        if not section:
            raise RuntimeError(f"Nacos 缺少配置: {key}")
        return section
