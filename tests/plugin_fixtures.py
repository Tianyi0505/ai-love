"""External test plugins exercise the public discovery/host/control contracts."""

from __future__ import annotations

import asyncio

from plugin_runtime import Plugin
from plugin_runtime.adapters import ScopedBus, ScopedScheduler
from shared.nats_bus import Bus, Subscription


class LocalSubscription(Subscription):
    def __init__(self, bus, subject, handler):
        self.bus, self.subject, self.handler = bus, subject, handler

    def unsubscribe(self):
        handlers = self.bus.handlers.get(self.subject, [])
        if self.handler in handlers:
            handlers.remove(self.handler)

    async def pause(self):
        self.unsubscribe()

    async def close(self):
        self.unsubscribe()


class LocalBus(Bus):
    def __init__(self):
        self.handlers = {}

    async def connect(self):
        pass

    async def close(self):
        self.handlers.clear()

    async def publish(self, subject, payload):
        for handler in list(self.handlers.get(subject, [])):
            await handler(payload)

    async def request(self, subject, payload, timeout):
        handlers = list(self.handlers.get(subject, []))
        if not handlers:
            raise RuntimeError("no responders")
        async with asyncio.timeout(timeout):
            return await handlers[0](payload)

    async def subscribe(self, subject, handler):
        self.handlers.setdefault(subject, []).append(handler)
        return LocalSubscription(self, subject, handler)

    async def reply(self, subject, handler):
        return await self.subscribe(subject, handler)


class EchoPlugin(Plugin):
    async def start(self):
        bus = ScopedBus(self.context.ports["bus"], self.context.resources)
        await bus.reply("test.echo", self.echo)
        ScopedScheduler(self.context.ports["scheduler"], self.context.resources).add_job(
            self.tick,
            "interval",
            seconds=3600,
        )
        self.context.provide("echo", self)

    async def echo(self, payload):
        if payload == b"slow":
            self.context.ports["entered"].set()
            await self.context.ports["release"].wait()
        return payload

    async def tick(self):
        pass


class DependentPlugin(Plugin):
    async def start(self):
        self.context.require("echo")
        self.context.provide("consumer", self)


class FailStartPlugin(Plugin):
    async def start(self):
        bus = ScopedBus(self.context.ports["bus"], self.context.resources)
        await bus.reply("test.failed", self.echo)
        raise ValueError("secret-value-that-must-not-reach-the-panel")

    async def echo(self, payload):
        return payload


class FailStopOncePlugin(EchoPlugin):
    async def stop(self):
        if not getattr(self, "failed_once", False):
            self.failed_once = True
            raise RuntimeError("temporary stop failure")
