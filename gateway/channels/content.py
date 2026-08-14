
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Type, TypeVar

from shared.contracts.social import ContentType

T = TypeVar("T")


# 表示内容类型判定上下文
@dataclass
class ContentContext:
    text: str = ""
    reply_id: str = ""
    forwards: list[dict] = field(default_factory=list)
    voices: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    at_targets: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    content_type: ContentType = ContentType.TEXT
    media: str = ""


# 定义内容类型判定策略
class ContentTypeStrategy(ABC):

    # 尝试按当前策略判定，返回是否命中
    @abstractmethod
    def apply(self, ctx: ContentContext) -> bool: ...


# 按优先级注册并执行内容判定策略
class ContentTypeRegistry:

    # 初始化当前实例
    def __init__(self) -> None:
        self._strategies: list[tuple[int, type[ContentTypeStrategy]]] = []

    # 注册策略装饰器
    def register(self, order: int) -> Callable[[Type[T]], Type[T]]:

        # 包装注册目标
        def deco(cls: Type[T]) -> Type[T]:
            self._strategies.append((order, cls))
            return cls

        return deco

    # 依次尝试策略直到命中
    def resolve(self, ctx: ContentContext) -> ContentContext:
        for _, cls in sorted(self._strategies, key=lambda item: item[0]):
            if cls().apply(ctx):
                break
        return ctx


content_registry = ContentTypeRegistry()


# 引用回复判定
@content_registry.register(order=10)
class QuoteStrategy(ContentTypeStrategy):

    # 尝试判定为引用回复
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.reply_id:
            return False
        ctx.content_type = ContentType.QUOTE
        ctx.meta["reply_message_id"] = ctx.reply_id
        return True


# 合并转发判定
@content_registry.register(order=20)
class ForwardStrategy(ContentTypeStrategy):

    # 尝试判定为合并转发
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.forwards:
            return False
        ctx.content_type = ContentType.FORWARD
        ctx.media = str(ctx.forwards[0].get("id", ""))
        inline = ctx.forwards[0].get("content")
        if isinstance(inline, list):
            ctx.meta["forward_inline"] = inline
        return True


# 语音判定
@content_registry.register(order=30)
class VoiceStrategy(ContentTypeStrategy):

    # 尝试判定为语音
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.voices:
            return False
        ctx.content_type = ContentType.VOICE
        ctx.media = str(ctx.voices[0].get("url", ""))
        return True


# 图片判定
@content_registry.register(order=40)
class ImageStrategy(ContentTypeStrategy):

    # 尝试判定为图片
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.images:
            return False
        ctx.content_type = ContentType.IMAGE
        ctx.media = str(ctx.images[0].get("url", ""))
        return True


# 文件判定
@content_registry.register(order=50)
class FileStrategy(ContentTypeStrategy):

    # 尝试判定为文件
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.files:
            return False
        ctx.content_type = ContentType.FILE
        ctx.media = str(ctx.files[0].get("url") or ctx.files[0].get("file") or "")
        ctx.text = ctx.text or str(ctx.files[0].get("name") or "文件")
        return True


# @提及判定
@content_registry.register(order=60)
class AtStrategy(ContentTypeStrategy):

    # 尝试判定为@提及
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.at_targets:
            return False
        ctx.content_type = ContentType.AT
        return True


# 纯文本兜底
@content_registry.register(order=100)
class TextStrategy(ContentTypeStrategy):

    # 兜底判定为纯文本
    def apply(self, ctx: ContentContext) -> bool:
        ctx.content_type = ContentType.TEXT
        return True
