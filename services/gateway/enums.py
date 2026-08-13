
from __future__ import annotations

from enum import Enum


class Channel(str, Enum):

    QQ = "qq"
    WECHAT = "wechat"
    BILIBILI = "bilibili"


class SendAction(str, Enum):

    PRIVATE_MSG = "send_private_msg"
    GROUP_MSG = "send_group_msg"


class SegmentType(str, Enum):

    TEXT = "text"
    AT = "at"
    IMAGE = "image"
    RECORD = "record"
    REPLY = "reply"
    FORWARD = "forward"


class EventPostType(str, Enum):

    MESSAGE = "message"
    REQUEST = "request"
    META = "meta_event"
