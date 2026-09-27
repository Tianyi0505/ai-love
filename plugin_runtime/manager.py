from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from .catalog import PluginCatalog
from .contracts import Plugin, PluginCommand, PluginContext, PluginError
from .resources import ResourceScope
from .store import PluginStore

logger = logging.getLogger("ailove.plugins")


@dataclass
class RunningPlugin:
    plugin: Plugin
    context: PluginContext


class PluginManager:
    """Serialize lifecycle transactions and expose capabilities only after startup succeeds."""

    def __init__(
        self,
        catalog: PluginCatalog,
        store: PluginStore,
        *,
        ports: dict | None = None,
        lifecycle_timeout: float = 30,
        drain_timeout: float = 60,
    ) -> None:
        self.catalog = catalog
        self.store = store
        self.ports = ports or {}
        self.lifecycle_timeout = lifecycle_timeout
        self.drain_timeout = drain_timeout
        self._instances: dict[str, RunningPlugin] = {}
        self._states: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._capabilities: dict[str, tuple[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._operation_task: asyncio.Task | None = None
        self._closing = False
        self._booting = True

    def resolve(self, capability: str) -> Any:
        if capability not in self._capabilities:
            raise PluginError(f"能力尚未就绪：{capability}", "unavailable")
        return self._capabilities[capability][1]

    def discover(self) -> None:
        previous = self.catalog.entries
        self.catalog.refresh()
        for plugin_id, running in self._instances.items():
            candidate = self.catalog.entries.get(plugin_id)
            if candidate is None or candidate.manifest != running.context.manifest:
                self.catalog.entries = previous
                raise PluginError(f"请先停用 {plugin_id} 再更换或移除其清单")
        for entry in self.catalog.entries.values():
            self.store.ensure(
                entry.manifest.id, entry.manifest.enabled if self._booting else False, installed=self._booting
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                [entry.manifest.model_dump() for _, entry in sorted(self.catalog.entries.items())],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.store.sync_catalog(fingerprint)

    async def start(self) -> None:
        self.discover()
        for plugin_id, state in self.store.states().items():
            if not state["installed"] or not state["enabled"]:
                continue
            try:
                plan = self._dependencies(plugin_id)
                for dependency in plan:
                    if not self.store.states()[dependency]["enabled"]:
                        raise PluginError(f"必需插件已停用：{dependency}")
                    await self._start(dependency)
            except Exception as exc:
                self._failure(plugin_id, "start", exc)
        self._booting = False

    def snapshot(self) -> dict:
        states = self.store.states()
        rows = []
        for plugin_id, state in states.items():
            entry = self.catalog.entries.get(plugin_id)
            manifest = entry.manifest if entry else None
            instance = self._instances.get(plugin_id)
            failure = instance.context.resources.failures if instance else []
            rows.append(
                {
                    "id": plugin_id,
                    "name": manifest.name if manifest else plugin_id,
                    "description": manifest.description if manifest else "清单已移除；保留操作记录",
                    "category": manifest.category if manifest else "unavailable",
                    "provides": list(manifest.provides) if manifest else [],
                    "requires": list(manifest.requires) if manifest else [],
                    "installed": bool(state["installed"]),
                    "enabled": bool(state["enabled"]),
                    "available": entry is not None,
                    "state": "failed"
                    if failure
                    else self._states.get(plugin_id, "disabled" if state["installed"] else "removed"),
                    "error": ("后台任务失败：" + ", ".join(failure)) if failure else self._errors.get(plugin_id),
                    "active_calls": instance.context.resources.active_calls if instance else 0,
                }
            )
        return {
            "host": self.catalog.host,
            "revision": self.store.revision,
            "plugins": rows,
            "catalog_errors": self.catalog.errors,
            "busy": self._booting or bool(self._operation_task and not self._operation_task.done()),
            "operations": self.store.recent_operations(),
        }

    def preflight(self, command: PluginCommand) -> dict:
        try:
            if command.expected_revision != self.store.revision:
                raise PluginError("插件状态已变化，请刷新后重试")
            affected = self._plan(command)
            return {"allowed": True, "affected": affected, "reason": None, "revision": self.store.revision}
        except PluginError as exc:
            return {
                "allowed": False,
                "affected": [],
                "reason": str(exc),
                "code": exc.code,
                "revision": self.store.revision,
            }

    async def submit(self, command: PluginCommand) -> dict:
        async with self._lock:
            existing = self.store.existing(command)
            if existing:
                return existing
            if self._closing:
                raise PluginError("宿主正在关闭", "unavailable")
            if self._booting:
                raise PluginError("宿主正在恢复插件状态，请稍后重试")
            if self._operation_task and not self._operation_task.done():
                raise PluginError("宿主有正在执行的插件操作，请等待完成")
            affected = self._plan(command)
            changes = {}
            for plugin_id in affected:
                installed = True
                enabled = command.action in {"enable", "restart"}
                changes[plugin_id] = (installed, enabled)
            operation = self.store.accept(command, changes)
            self._operation_task = asyncio.create_task(self._execute(command, affected))
            return operation

    def _plan(self, command: PluginCommand) -> list[str]:
        states = self.store.states()
        if command.plugin_id not in states:
            raise PluginError("未发现插件，请先刷新本地插件目录", "not_found")
        if command.action == "install":
            self._entry(command.plugin_id)
            if states[command.plugin_id]["installed"]:
                raise PluginError("插件已经安装")
            return [command.plugin_id]
        if not states[command.plugin_id]["installed"]:
            raise PluginError("请先安装插件")
        if command.action == "enable":
            return self._dependencies(command.plugin_id)
        affected = self._dependents(command.plugin_id)
        if len(affected) > 1 and not command.stop_dependents:
            raise PluginError("需要一并停止依赖插件：" + "、".join(affected[:-1]))
        if command.action == "restart":
            for dependency in self._dependencies(command.plugin_id):
                if dependency != command.plugin_id and self._states.get(dependency) != "active":
                    raise PluginError(f"必需能力尚未启动：{dependency}；请使用启用操作")
        return affected

    def _entry(self, plugin_id: str):
        entry = self.catalog.entries.get(plugin_id)
        if entry is None:
            raise PluginError(f"插件清单不可用：{plugin_id}", "not_found")
        return entry

    def _dependencies(self, plugin_id: str) -> list[str]:
        ordered, visiting = [], set()
        states = self.store.states()

        def visit(current: str) -> None:
            if current in visiting:
                raise PluginError(f"插件能力依赖成环：{current}")
            if current in ordered:
                return
            if not states.get(current, {}).get("installed"):
                raise PluginError(f"插件未安装：{current}")
            visiting.add(current)
            for capability in self._entry(current).manifest.requires:
                providers = [
                    key
                    for key, entry in self.catalog.entries.items()
                    if capability in entry.manifest.provides and states.get(key, {}).get("installed")
                ]
                if len(providers) != 1:
                    raise PluginError(f"能力 {capability} 必须有唯一已安装提供者，当前为 {len(providers)} 个")
                visit(providers[0])
            visiting.remove(current)
            ordered.append(current)

        visit(plugin_id)
        return ordered

    def _dependents(self, plugin_id: str) -> list[str]:
        ordered, visiting = [], set()
        states = self.store.states()

        def visit(current: str) -> None:
            if current in ordered or current in visiting:
                return
            visiting.add(current)
            entry = self.catalog.entries.get(current)
            instance = self._instances.get(current)
            manifest = instance.context.manifest if instance else (entry.manifest if entry else None)
            provided = set(manifest.provides) if manifest else set()
            for key, candidate in self.catalog.entries.items():
                if key == current or not (key in self._instances or states.get(key, {}).get("enabled")):
                    continue
                if provided.intersection(candidate.manifest.requires):
                    visit(key)
            ordered.append(current)

        visit(plugin_id)
        return ordered

    async def _execute(self, command: PluginCommand, affected: list[str]) -> None:
        self.store.finish(command.operation_id, "running")
        try:
            if command.action in {"disable", "restart", "remove"}:
                for plugin_id in affected:
                    await self._stop(plugin_id)
            if command.action in {"enable", "restart"}:
                for plugin_id in reversed(affected) if command.action == "restart" else affected:
                    for dependency in self._dependencies(plugin_id):
                        if not self.store.states()[dependency]["enabled"]:
                            raise PluginError(f"必需插件已停用：{dependency}")
                        await self._start(dependency)
            if command.action in {"install", "remove"}:
                if command.action == "remove":
                    self.store.uninstall(command.plugin_id)
                self._states[command.plugin_id] = "disabled" if command.action == "install" else "removed"
            self.store.finish(command.operation_id, "completed")
        except Exception as exc:
            error = str(exc) if isinstance(exc, PluginError) else f"操作失败：{type(exc).__name__}；请检查宿主日志"
            self.store.finish(command.operation_id, "failed", error)

    async def _start(self, plugin_id: str) -> None:
        if self._states.get(plugin_id) == "active":
            return
        if plugin_id in self._instances:
            raise PluginError(f"{plugin_id} 有未清理资源，请先重试停用")
        entry = self._entry(plugin_id)
        for capability in entry.manifest.requires:
            self.resolve(capability)
        for capability in entry.manifest.provides:
            if capability in self._capabilities:
                raise PluginError(f"能力已有活动提供者：{capability}")
        context = PluginContext(entry.manifest, ResourceScope(), self, self.ports, entry.manifest.config)
        self._states[plugin_id] = "starting"
        stage = "load"
        try:
            plugin = entry.create()
            self._instances[plugin_id] = RunningPlugin(plugin, context)
            async with asyncio.timeout(self.lifecycle_timeout):
                stage = "initialize"
                await plugin.initialize(context)
                stage = "start"
                await plugin.start()
                if set(context._exports) != set(entry.manifest.provides):
                    raise PluginError("插件未提供清单声明的全部能力")
            self._capabilities.update({key: (plugin_id, value) for key, value in context._exports.items()})
            self._states[plugin_id] = "active"
            self._errors.pop(plugin_id, None)
        except BaseException as exc:
            if plugin_id in self._instances:
                try:
                    await self._stop(plugin_id)
                except Exception:
                    logger.error("[%s] 初始化失败后的资源回收未完成", plugin_id)
            self._failure(plugin_id, stage, exc)
            raise

    async def _stop(self, plugin_id: str) -> None:
        running = self._instances.get(plugin_id)
        if running is None:
            self._states[plugin_id] = "disabled"
            self._errors.pop(plugin_id, None)
            return
        self._states[plugin_id] = "draining"
        for capability in running.context.manifest.provides:
            self._capabilities.pop(capability, None)
        stage = "drain"
        try:
            async with asyncio.timeout(self.drain_timeout):
                await running.context.resources.quiesce()
                await running.context.resources.drain()
            stage = "stop"
            async with asyncio.timeout(self.lifecycle_timeout):
                await running.plugin.stop()
            stage = "dispose"
            async with asyncio.timeout(self.lifecycle_timeout):
                await running.plugin.dispose()
                await running.context.resources.close()
            del self._instances[plugin_id]
            self._states[plugin_id] = "disabled"
            self._errors.pop(plugin_id, None)
        except BaseException as exc:
            self._failure(plugin_id, stage, exc)
            raise

    def _failure(self, plugin_id: str, stage: str, exc: BaseException) -> None:
        detail = str(exc) if isinstance(exc, PluginError) else type(exc).__name__
        self._states[plugin_id] = "failed"
        self._errors[plugin_id] = f"{stage}: {detail}；可重试停用以回收资源，随后重新启用"
        logger.error("[%s] %s failed (%s)", plugin_id, stage, type(exc).__name__)

    async def close(self) -> None:
        self._closing = True
        if self._operation_task:
            await self._operation_task
        errors = []
        for plugin_id in list(reversed(self._instances)):
            try:
                await self._stop(plugin_id)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("部分插件未完成停用", errors)
