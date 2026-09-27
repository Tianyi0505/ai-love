"""Scope host infrastructure so plugins cannot leave listeners and jobs behind."""

from __future__ import annotations

from shared.nats_bus import Bus

from .resources import ResourceScope


class ScopedASGI:
    """Reject new HTTP work during drain while existing requests finish normally."""

    def __init__(self, app, resources: ResourceScope) -> None:
        self.app = app
        self.resources = resources

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if not self.resources.accepting:
            await send(
                {"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"application/json")]}
            )
            await send({"type": "http.response.body", "body": b'{"detail":"plugin unavailable"}'})
            return
        async with self.resources.call():
            await self.app(scope, receive, send)


class ScopedBus(Bus):
    def __init__(self, bus: Bus, scope: ResourceScope) -> None:
        self._bus = bus
        self._scope = scope

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass  # The host owns the shared connection.

    async def publish(self, subject, payload):
        await self._bus.publish(subject, payload)

    async def request(self, subject, payload, timeout):
        return await self._bus.request(subject, payload, timeout)

    async def publish_durable(self, subject, payload):
        await self._bus.publish_durable(subject, payload)

    async def ensure_stream(self, name, subjects):
        await self._bus.ensure_stream(name, subjects)

    async def key_value(self, bucket):
        return await self._bus.key_value(bucket)

    async def subscribe(self, subject, handler):
        return self._own(await self._bus.subscribe(subject, self._scope.guard(handler)))

    async def reply(self, subject, handler):
        return self._own(await self._bus.reply(subject, self._scope.guard(handler)))

    async def subscribe_durable(self, subject, durable, queue, handler):
        return self._own(await self._bus.subscribe_durable(subject, durable, queue, self._scope.guard(handler)))

    def _own(self, subscription):
        # Quiescing stops ingress without cancelling a callback that already started.
        self._scope.on_quiesce(subscription.pause)
        self._scope.defer(subscription.close)
        return subscription


class ScopedScheduler:
    def __init__(self, scheduler, scope: ResourceScope) -> None:
        self._scheduler = scheduler
        self._scope = scope

    def add_job(self, callback, *args, **kwargs):
        job = self._scheduler.add_job(self._scope.guard(callback), *args, **kwargs)

        def remove():
            if self._scheduler.get_job(job.id) is not None:
                self._scheduler.remove_job(job.id)

        self._scope.on_quiesce(remove)
        return job


class ScopedConfigProvider:
    def __init__(self, provider, scope: ResourceScope) -> None:
        self._provider = provider
        self._scope = scope

    async def get(self, key):
        return await self._provider.get(key)

    async def watch(self, key, callback):
        remove = await self._provider.watch(key, self._scope.guard(callback))
        if callable(remove):
            self._scope.on_quiesce(remove)

    async def close(self):
        pass


class ScopedServiceConfig:
    def __init__(self, config, scope: ResourceScope) -> None:
        self._config = config
        self.config_provider = ScopedConfigProvider(config.config_provider, scope)

    def __getattr__(self, name):
        # Delegate reads to the live configuration instead of copying its current snapshot.
        return getattr(self._config, name)


def scoped_config(config, scope: ResourceScope) -> ScopedServiceConfig:
    return ScopedServiceConfig(config, scope)
