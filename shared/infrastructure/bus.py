
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


# 定义订阅接口
class Subscription(ABC):
    # 取消消息订阅
    @abstractmethod
    def unsubscribe(self) -> None: ...


# 定义消息总线接口
class Bus(ABC):

    # 建立连接
    @abstractmethod
    async def connect(self) -> None: ...

    # 关闭资源
    @abstractmethod
    async def close(self) -> None: ...

    # 发布消息
    @abstractmethod
    async def publish(self, subject: str, payload: bytes) -> None: ...

    # 订阅消息
    @abstractmethod
    async def subscribe(self, subject: str, handler: Handler) -> Subscription: ...

    # 发送请求
    @abstractmethod
    async def request(self, subject: str, payload: bytes, timeout: float) -> bytes: ...

    # 注册请求响应处理器
    @abstractmethod
    async def reply(self, subject: str, handler: Handler) -> Subscription: ...

    # 发布JSON
    async def publish_json(self, subject: str, obj: dict) -> None:
        await self.publish(subject, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    # 发送JSON请求
    async def request_json(self, subject: str, obj: dict, timeout: float) -> dict:
        raw = await self.request(subject, json.dumps(obj, ensure_ascii=False).encode("utf-8"), timeout)
        return json.loads(raw.decode("utf-8"))

    # 向持久化主题发布消息
    async def publish_durable(self, subject: str, payload: bytes) -> None:
        raise NotImplementedError

    # 向持久化主题发布JSON消息
    async def publish_durable_json(self, subject: str, obj: dict) -> None:
        await self.publish_durable(
            subject,
            json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        )

    # 确保直播流
    async def ensure_stream(self, name: str, subjects: list[str]) -> None:
        raise NotImplementedError

    # 获取键值存储
    async def key_value(self, bucket: str):
        raise NotImplementedError

    # 创建持久化消息订阅
    async def subscribe_durable(
        self,
        subject: str,
        durable: str,
        queue: str,
        handler: Handler,
    ) -> Subscription:
        raise NotImplementedError


# 通过NATS发布和订阅消息
class NATSBus(Bus):

    # 初始化当前实例
    def __init__(self, url: str | None, token: str | None) -> None:
        self._url = required_setting(url, ConfigKey.AILOVE_BUS_URL)
        self._token = token
        self._conn = None
        self._jetstream = None

    # 建立连接
    async def connect(self) -> None:
        if self._token:
            self._conn = await nats.connect(self._url, token=self._token)
        else:
            self._conn = await nats.connect(self._url)
        self._jetstream = self._conn.jetstream()

    # 关闭资源
    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._jetstream = None

    # 发布消息
    async def publish(self, subject: str, payload: bytes) -> None:
        await self._conn.publish(subject, payload)

    # 向持久化主题发布消息
    async def publish_durable(self, subject: str, payload: bytes) -> None:
        await self._jetstream.publish(subject, payload)

    # 订阅消息
    async def subscribe(self, subject: str, handler: Handler) -> Subscription:
        sub = await self._conn.subscribe(subject)

        # 持续消费消息
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

    # 发送请求
    async def request(self, subject: str, payload: bytes, timeout: float) -> bytes:
        msg = await self._conn.request(subject, payload, timeout=timeout)
        return msg.data

    # 注册请求响应处理器
    async def reply(self, subject: str, handler: Handler) -> Subscription:
        return await self.subscribe(subject, handler)

    # 确保直播流
    async def ensure_stream(self, name: str, subjects: list[str]) -> None:
        try:
            await self._jetstream.stream_info(name)
        except NotFoundError:
            await self._jetstream.add_stream(name=name, subjects=subjects)

    # 获取键值存储
    async def key_value(self, bucket: str):
        try:
            return await self._jetstream.key_value(bucket)
        except BucketNotFoundError:
            return await self._jetstream.create_key_value(bucket=bucket, history=1)

    # 创建持久化消息订阅
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

        # 持续消费消息
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


# 封装消息订阅回调
class _SubWrapper(Subscription):
    # 初始化当前实例
    def __init__(self, task) -> None:
        self._task = task

    # 取消消息订阅
    def unsubscribe(self) -> None:
        self._task.cancel()


# 创建消息总线
def create_bus(url: str | None, token: str | None) -> Bus:
    return NATSBus(url, token)
