from __future__ import annotations

from enum import Enum


class LLMErrorMessage(str, Enum):
    NO_PROVIDER = "无可用大模型提供者"
    START_FAILED = "流式请求启动失败"
    FIRST_PACKET_TIMEOUT = "流式首包超时"
    NO_CONTENT = "流式请求未返回内容"
    ALL_FAILED = "大模型调用失败，请稍后再试..."
