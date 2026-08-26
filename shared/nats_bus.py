from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Generic, TypeVar

import nats
from nats.js.errors import BucketNotFoundError, NotFoundError
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel, ConfigDict

Handler = Callable[[bytes], Awaitable[bytes | None]]
ModelT = TypeVar("ModelT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)
logger = logging.getLogger("ailove.bus")
tracer = trace.get_tracer("ai-love.nats")


def _span_attributes(subject: str, operation: str) -> dict[str, str]:
    return {
        "messaging.system": "nats",
        "messaging.destination.name": subject,
        "messaging.operation.name": operation,
    }


class RpcError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class RpcEnvelope(BaseModel, Generic[ResponseT]):
    model_config = ConfigDict(extra="forbid")

    data: ResponseT | None = None
    error: RpcError | None = None


class RemoteCallError(RuntimeError):
    def __init__(self, error: RpcError) -> None:
        super().__init__(f"{error.code}: {error.message}")
        self.code = error.code


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

    async def publish_model(self, subject: str, message: BaseModel) -> None:
        await self.publish(subject, message.model_dump_json().encode("utf-8"))

    async def subscribe_model(
        self,
        subject: str,
        message_type: type[ModelT],
        handler: Callable[[ModelT], Awaitable[None]],
    ) -> Subscription:
        async def typed_handler(payload: bytes) -> None:
            await handler(message_type.model_validate_json(payload))

        return await self.subscribe(subject, typed_handler)

    async def request_model(
        self,
        subject: str,
        request: BaseModel,
        response_type: type[ResponseT],
        timeout: float,
    ) -> ResponseT:
        raw = await self.request(subject, request.model_dump_json().encode("utf-8"), timeout)
        envelope = RpcEnvelope[response_type].model_validate_json(raw)
        if envelope.error is not None:
            raise RemoteCallError(envelope.error)
        if envelope.data is None:
            raise RuntimeError(f"{subject} 返回空响应")
        return envelope.data

    async def reply_model(
        self,
        subject: str,
        request_type: type[ModelT],
        response_type: type[ResponseT],
        handler: Callable[[ModelT], Awaitable[ResponseT]],
    ) -> Subscription:
        async def typed_handler(payload: bytes) -> bytes:
            try:
                request = request_type.model_validate_json(payload)
                response = await handler(request)
                envelope = RpcEnvelope[response_type](data=response)
            except Exception as exc:
                span = trace.get_current_span()
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                envelope = RpcEnvelope[response_type](error=RpcError(code=exc.__class__.__name__, message=str(exc)))
            return envelope.model_dump_json().encode("utf-8")

        return await self.reply(subject, typed_handler)

    # 向持久化主题发布消息
    async def publish_durable(self, subject: str, payload: bytes) -> None:
        raise NotImplementedError

    async def publish_durable_model(self, subject: str, message: BaseModel) -> None:
        await self.publish_durable(subject, message.model_dump_json().encode("utf-8"))

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

    async def subscribe_durable_model(
        self,
        subject: str,
        durable: str,
        queue: str,
        message_type: type[ModelT],
        handler: Callable[[ModelT], Awaitable[None]],
    ) -> Subscription:
        async def typed_handler(payload: bytes) -> None:
            await handler(message_type.model_validate_json(payload))

        return await self.subscribe_durable(subject, durable, queue, typed_handler)


# 通过NATS发布和订阅消息
class NATSBus(Bus):
    # 初始化当前实例
    def __init__(self, url: str, token: str | None) -> None:
        self._url = url
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
        with tracer.start_as_current_span(
            f"{subject} publish",
            kind=SpanKind.PRODUCER,
            attributes=_span_attributes(subject, "publish"),
        ):
            headers: dict[str, str] = {}
            propagate.inject(headers)
            await self._conn.publish(subject, payload, headers=headers)

    # 向持久化主题发布消息
    async def publish_durable(self, subject: str, payload: bytes) -> None:
        with tracer.start_as_current_span(
            f"{subject} publish",
            kind=SpanKind.PRODUCER,
            attributes=_span_attributes(subject, "publish"),
        ):
            headers: dict[str, str] = {}
            propagate.inject(headers)
            await self._jetstream.publish(subject, payload, headers=headers)

    # 订阅消息
    async def subscribe(self, subject: str, handler: Handler) -> Subscription:
        sub = await self._conn.subscribe(subject)

        # 持续消费消息
        async def pump() -> None:
            async for msg in sub.messages:
                parent = propagate.extract(dict(msg.headers) if msg.headers is not None else {})
                with tracer.start_as_current_span(
                    f"{subject} process",
                    context=parent,
                    kind=SpanKind.CONSUMER,
                    attributes=_span_attributes(subject, "process"),
                ):
                    result = await handler(msg.data)
                    if result is not None and msg.reply:
                        await msg.respond(result)

        task = asyncio.create_task(pump())
        return _SubWrapper(task)

    # 发送请求
    async def request(self, subject: str, payload: bytes, timeout: float) -> bytes:
        with tracer.start_as_current_span(
            f"{subject} request",
            kind=SpanKind.CLIENT,
            attributes=_span_attributes(subject, "request"),
        ):
            headers: dict[str, str] = {}
            propagate.inject(headers)
            msg = await self._conn.request(subject, payload, timeout=timeout, headers=headers)
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
                parent = propagate.extract(dict(msg.headers) if msg.headers is not None else {})
                with tracer.start_as_current_span(
                    f"{subject} process",
                    context=parent,
                    kind=SpanKind.CONSUMER,
                    attributes=_span_attributes(subject, "process"),
                ):
                    await handler(msg.data)
                    await msg.ack()

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
def create_bus(url: str, token: str | None) -> Bus:
    return NATSBus(url, token)
