from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from shared.config_provider import ConfigProvider, ConfigurationError
from shared.connection_settings import ServiceConnectionSettings
from shared.mounted_config_provider import MountedConfigProvider
from shared.service_settings import ServiceIdentitySettings
from shared.snowflake_id_generator import snowflake_ids

SettingsT = TypeVar("SettingsT", bound=BaseModel)


# 表示服务配置数据
@dataclass
class ServiceConfig:
    service_name: str
    config_provider: ConfigProvider
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
        provider = MountedConfigProvider()
        try:
            await provider.connect()
            connection = ServiceConnectionSettings()
            section = None
            for attempt in range(connection.config_retry_count):
                try:
                    section = await provider.get(f"service.{service_name}")
                    break
                except ConfigurationError:
                    if attempt + 1 == connection.config_retry_count:
                        raise
                    await asyncio.sleep(connection.config_retry_interval_sec)
            if section is None:
                raise RuntimeError(f"配置重试次数必须大于零: service.{service_name}")
            identity = ServiceIdentitySettings.model_validate(section)
            cfg = cls(
                service_name=service_name,
                config_provider=provider,
                bus_url=connection.bus_url,
                bus_token=connection.bus_token,
                instance_addr=identity.instance_addr,
            )
            cfg._section = section
            cfg._section_key = f"service.{service_name}"
            await cfg._subscribe()
            return cfg
        except BaseException:
            await provider.close()
            raise

    # 订阅消息
    async def _subscribe(self) -> None:
        if self._watching:
            return
        self._watching = True

        # 处理配置变更
        async def _on_change(data_id: str, parsed: dict) -> None:
            if not parsed:
                raise RuntimeError(f"配置 {data_id} 不能为空")
            self._section = parsed

        await self.config_provider.watch(self._section_key, _on_change)

    # 读取配置段
    async def section(self, settings_type: type[SettingsT]) -> SettingsT:
        return settings_type.model_validate(self._section)

    # 加载导演配置
    async def director(self, session_id: str, settings_type: type[SettingsT]) -> SettingsT:
        key = f"director.{session_id}"
        section = await self.config_provider.get(key)
        if not section:
            raise RuntimeError(f"缺少配置: {key}")
        return settings_type.model_validate(section)
