from __future__ import annotations

import asyncio
import json

from pydantic import ValidationError

from .contracts import PluginCommand, PluginError


class PluginControlServer:
    def __init__(self, manager, bus) -> None:
        self.manager = manager
        self.bus = bus
        self.subscription = None

    async def start(self) -> None:
        self.subscription = await self.bus.reply(f"ailove.plugins.{self.manager.catalog.host}", self.handle)

    async def handle(self, payload: bytes) -> bytes:
        try:
            request = json.loads(payload)
            method = request["method"]
            if method == "list":
                result = self.manager.snapshot()
            elif method == "refresh":
                if self.manager.snapshot()["busy"]:
                    raise PluginError("请等待当前插件操作完成")
                self.manager.discover()
                result = self.manager.snapshot()
            elif method == "preflight":
                result = self.manager.preflight(PluginCommand.model_validate(request["command"]))
            elif method == "submit":
                result = await self.manager.submit(PluginCommand.model_validate(request["command"]))
            elif method == "operation":
                result = self.manager.store.operation(request["operation_id"])
                if result is None:
                    raise PluginError("操作记录不存在", "not_found")
            else:
                raise PluginError("未知插件管理方法", "invalid")
            return json.dumps({"data": result}, ensure_ascii=False).encode()
        except PluginError as exc:
            error = {"code": exc.code, "message": str(exc)}
        except (ValueError, KeyError, TypeError, ValidationError):
            error = {"code": "invalid", "message": "插件管理请求格式无效"}
        except Exception:
            error = {"code": "unavailable", "message": "插件控制面暂时不可用"}
        return json.dumps({"error": error}, ensure_ascii=False).encode()

    async def close(self) -> None:
        if self.subscription:
            await self.subscription.close()


class PluginControlClient:
    def __init__(self, bus, hosts: tuple[str, ...]) -> None:
        self.bus = bus
        self.hosts = hosts
        self._connected = False
        self._connect_lock = asyncio.Lock()

    async def call(self, host: str, method: str, **data) -> dict:
        if host not in self.hosts:
            raise PluginError("未知插件宿主", "not_found")
        await self._connect()
        try:
            response = await self.bus.request(
                f"ailove.plugins.{host}", json.dumps({"method": method, **data}).encode(), timeout=5
            )
        except Exception:
            self._connected = False
            raise
        payload = json.loads(response)
        if "error" in payload:
            raise PluginError(payload["error"]["message"], payload["error"]["code"])
        return payload["data"]

    async def _connect(self) -> None:
        async with self._connect_lock:
            if not self._connected:
                async with asyncio.timeout(5):
                    await self.bus.connect()
                self._connected = True

    async def list_hosts(self) -> dict:
        def offline(host):
            return {
                "host": host,
                "online": False,
                "plugins": [],
                "revision": 0,
                "error": "宿主未连接或控制面不可用",
                "operations": [],
                "busy": False,
            }

        try:
            await self._connect()
        except Exception:
            return {"hosts": [offline(host) for host in self.hosts]}

        async def read(host):
            try:
                return {"online": True, **await self.call(host, "list")}
            except Exception:
                return offline(host)

        return {"hosts": await asyncio.gather(*(read(host) for host in self.hosts))}

    async def close(self) -> None:
        await self.bus.close()
        self._connected = False
