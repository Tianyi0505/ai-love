"""A minimal trusted plugin: no changes to the host or management UI required."""

from plugin_runtime import Plugin
from plugin_runtime.adapters import ScopedBus


class EchoPlugin(Plugin):
    async def start(self) -> None:
        bus = ScopedBus(self.context.ports["bus"], self.context.resources)
        await bus.reply("example.echo", self.echo)
        self.context.provide("example.echo", self)

    async def echo(self, payload: bytes) -> bytes:
        return payload
