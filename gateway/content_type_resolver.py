from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from shared.contracts.social import ContentType


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


# 按优先级执行内容判定策略
class ContentTypeResolver:
    def __init__(self, strategies: Sequence[ContentTypeStrategy]) -> None:
        self._strategies = tuple(strategies)

    # 依次尝试策略直到命中
    def resolve(self, ctx: ContentContext) -> ContentContext:
        for strategy in self._strategies:
            if strategy.apply(ctx):
                break
        return ctx


# 引用回复判定
class QuoteStrategy(ContentTypeStrategy):
    # 尝试判定为引用回复
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.reply_id:
            return False
        ctx.content_type = ContentType.QUOTE
        ctx.meta["reply_message_id"] = ctx.reply_id
        return True


# 合并转发判定
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
class VoiceStrategy(ContentTypeStrategy):
    # 尝试判定为语音
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.voices:
            return False
        ctx.content_type = ContentType.VOICE
        ctx.media = str(ctx.voices[0].get("url", ""))
        return True


# 图片判定
class ImageStrategy(ContentTypeStrategy):
    # 尝试判定为图片
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.images:
            return False
        ctx.content_type = ContentType.IMAGE
        ctx.media = str(ctx.images[0].get("url", ""))
        return True


# 文件判定
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
class AtStrategy(ContentTypeStrategy):
    # 尝试判定为@提及
    def apply(self, ctx: ContentContext) -> bool:
        if not ctx.at_targets:
            return False
        ctx.content_type = ContentType.AT
        return True


# 纯文本判定
class TextStrategy(ContentTypeStrategy):
    # 判定为纯文本
    def apply(self, ctx: ContentContext) -> bool:
        ctx.content_type = ContentType.TEXT
        return True
