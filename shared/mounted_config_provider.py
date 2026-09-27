from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_provider import ConfigListener, ConfigProvider, ConfigurationError, Unsubscribe

logger = logging.getLogger("ailove.config")


class MountedConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AILOVE_CONFIG_", extra="ignore")

    directory: Path = Path("deploy/config")
    secret_directory: Path | None = None
    poll_interval_sec: float = Field(default=2, gt=0)


def merge_config(base: dict, overlay: dict) -> dict:
    """Merge Secret overlays without mutating either input; lists replace atomically."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class MountedConfigProvider(ConfigProvider):
    """Read Kubernetes projected ConfigMap/Secret volumes without cluster credentials.

    Reopen paths on every read so kubelet's atomic symlink swaps are observed. Mount
    the whole directory, never a subPath. Local development uses the same YAML contract.
    """

    def __init__(self, settings: MountedConfigSettings | None = None) -> None:
        self.settings = settings or MountedConfigSettings()
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    async def connect(self) -> None:
        if not self.settings.directory.is_dir():
            raise ConfigurationError("配置目录未挂载，请检查 ConfigMap 卷或 AILOVE_CONFIG_DIRECTORY")
        if self.settings.secret_directory is not None and not self.settings.secret_directory.is_dir():
            raise ConfigurationError("敏感配置目录未挂载，请检查 Secret 卷")

    @staticmethod
    def _document(directory: Path, key: str, *, optional: bool = False) -> dict:
        path = directory / f"{key}.yaml"
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if optional:
                return {}
            raise ConfigurationError(f"配置不存在：{key}") from None
        except OSError:
            raise ConfigurationError(f"配置暂不可读：{key}") from None
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            raise ConfigurationError(f"配置 YAML 无效：{key}") from None
        if not isinstance(data, dict):
            raise ConfigurationError(f"配置必须为对象：{key}")
        return data

    async def get(self, key: str) -> dict:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,199}", key):
            raise ConfigurationError("无效配置标识")
        data = self._document(self.settings.directory, key)
        if self.settings.secret_directory:
            overlay = self._document(self.settings.secret_directory, key, optional=True)
            data = merge_config(data, overlay)
        return data

    @staticmethod
    def _fingerprint(data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    async def watch(self, key: str, callback: ConfigListener) -> Unsubscribe:
        if self._closed:
            raise ConfigurationError("配置提供器已关闭")
        # Reconcile immediately: an update between the caller's get() and watch()
        # must not be silently skipped.
        initial = await self.get(key)
        await callback(key, initial)
        revision = self._fingerprint(initial)

        async def poll() -> None:
            nonlocal revision
            while True:
                await asyncio.sleep(self.settings.poll_interval_sec)
                try:
                    data = await self.get(key)
                    candidate = self._fingerprint(data)
                    if candidate != revision:
                        await callback(key, data)
                        revision = candidate
                except Exception as exc:
                    # A failed listener retains its last good state and retries. Never log values.
                    logger.warning("配置更新暂未应用：%s (%s)", key, type(exc).__name__)

        task = asyncio.create_task(poll(), name=f"config:{key}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        async def remove() -> None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        return remove

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
