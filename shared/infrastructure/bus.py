
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

import nats
from nats.js.errors import BucketNotFoundError, NotFoundError

from shared.infrastructure.runtime_config import ConfigKey, required_setting

Handler = Callable[[bytes], Awaitable[bytes | None]]
logger = logging.getLogger("ailove.bus")


class Subscription(ABC):
    @abstractmethod
    def unsubscribe(self) -> None: ...


class Bus(ABC):

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def publish(self, subject: str, payload: bytes) -> None: ...

    @abstractmethod
    async def subscribe(self, subject: str, handler: Handler) -> Subscription: ...

    @abstractmethod
    async def request(self, subject: str, payload: bytes, timeout: float) -> bytes: ...

    @abstractmethod
    async def reply(self, subject: str, handler: Handler) -> Subscription: ...

    async def publish_json(self, subject: str, obj: dict) -> None:
        await self.publish(subject, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    async def request_json(self, subject: str, obj: dict, timeout: float) -> dict:
        raw = await self.request(subject, json.dumps(obj, ensure_ascii=False).encode("utf-8"), timeout)
        return json.loads(raw.decode("utf-8"))

    async def publish_durable(self, subject: str, payload: bytes) -> None:
        raise NotImplementedError

    async def publish_durable_json(self, subject: str, obj: dict) -> None:
        await self.publish_durable(
            subject,
            json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        )

    async def ensure_stream(self, name: str, subjects: list[str]) -> None:
        raise NotImplementedError

    async def key_value(self, bucket: str):
        raise NotImplementedError

    async def subscribe_durable(
        self,
        subject: str,
        durable: str,
        queue: str,
        handler: Handler,
    ) -> Subscription:
        raise NotImplementedError


class NATSBus(Bus):

    def __init__(self, url: str | None, token: str | None) -> None:
        self._url = required_setting(url, ConfigKey.AILOVE_BUS_URL)
        self._token = token
        self._conn = None
        self._jetstream = None

    async def connect(self) -> None:
        if self._token:
            self._conn = await nats.connect(self._url, token=self._token)
        else:
            self._conn = await nats.connect(self._url)
        self._jetstream = self._conn.jetstream()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._jetstream = None

    async def publish(self, subject: str, payload: bytes) -> None:
        await self._conn.publish(subject, payload)

    async def publish_durable(self, subject: str, payload: bytes) -> None:
        await self._jetstream.publish(subject, payload)

    async def subscribe(self, subject: str, handler: Handler) -> Subscription:
        sub = await self._conn.subscribe(subject)

        async def pump() -> None:
            async for msg in sub.messages:
                try:
                    result = await handler(msg.data)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("[bus] 消息处理失败，继续消费: subject=%s", msg.subject)
                    if msg.reply:
                        try:
                            await msg.respond(b'{"ok":false,"error":"handler_failed"}')
                        except Exception:
                            logger.exception("[bus] 发送失败响应异常: subject=%s", msg.subject)
                    continue
                if result is not None and msg.reply:
                    await msg.respond(result)

        task = asyncio.create_task(pump())
        return _SubWrapper(task)

    async def request(self, subject: str, payload: bytes, timeout: float) -> bytes:
        msg = await self._conn.request(subject, payload, timeout=timeout)
        return msg.data

    async def reply(self, subject: str, handler: Handler) -> Subscription:
        return await self.subscribe(subject, handler)

    async def ensure_stream(self, name: str, subjects: list[str]) -> None:
        try:
            await self._jetstream.stream_info(name)
        except NotFoundError:
            await self._jetstream.add_stream(name=name, subjects=subjects)

    async def key_value(self, bucket: str):
        try:
            return await self._jetstream.key_value(bucket)
        except BucketNotFoundError:
            return await self._jetstream.create_key_value(bucket=bucket, history=1)

    async def subscribe_durable(
        self,
        subject: str,
        durable: str,
        queue: str,
        handler: Handler,
    ) -> Subscription:
        sub = await self._jetstream.subscribe(
            subject,
            queue=queue,
            durable=durable,
            manual_ack=True,
        )

        async def pump() -> None:
            async for msg in sub.messages:
                try:
                    await handler(msg.data)
                    await msg.ack()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("[bus] JetStream 消息处理失败: subject=%s", msg.subject)
                    await msg.nak(delay=1)

        return _SubWrapper(asyncio.create_task(pump()))


class _SubWrapper(Subscription):
    def __init__(self, task) -> None:
        self._task = task

    def unsubscribe(self) -> None:
        self._task.cancel()


def create_bus(url: str | None, token: str | None) -> Bus:
    return NATSBus(url, token)
