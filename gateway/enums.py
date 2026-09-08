from __future__ import annotations

from enum import Enum


# 定义渠道枚举
class Channel(str, Enum):
    QQ = "qq"
    WECHAT = "wechat"
    BILIBILI = "bilibili"


# 定义发送动作枚举
class SendAction(str, Enum):
    PRIVATE_MSG = "send_private_msg"
    GROUP_MSG = "send_group_msg"


# 定义消息段类型枚举
class SegmentType(str, Enum):
    TEXT = "text"
    FACE = "face"
    AT = "at"
    IMAGE = "image"
    RECORD = "record"
    REPLY = "reply"
    FORWARD = "forward"


# 定义事件提交请求类型枚举
class EventPostType(str, Enum):
    MESSAGE = "message"
    REQUEST = "request"
    META = "meta_event"
