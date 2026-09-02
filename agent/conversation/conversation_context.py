from __future__ import annotations

from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

ConversationEntry = tuple[str, str, dict]

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def format_entries(entries, ai_name: str = "") -> str:
    blocks: list[str] = []
    for role, text, meta in entries:
        timestamp = str(meta.get("timestamp", ""))
        time_label = f"[{timestamp}] " if timestamp else ""
        if role == "assistant":
            label = f"[AI | {ai_name}]" if ai_name else "[AI]"
            blocks.append(f"{time_label}{label}\n{text}")
            continue
        name = str(meta["speaker_name"])
        person_id = str(meta["speaker_id"])
        label = f"[{person_id} | {name}]" if person_id else f"[{name}]"
        quote = meta.get("quote")
        if quote is not None:
            blocks.append(f"{time_label}{label}\n[引用 {quote['name']}]\n{text}")
        else:
            blocks.append(f"{time_label}{label}\n{text}")
    return "\n\n".join(blocks)


class ConversationContext:
    def __init__(self, window_size: int, timezone: str = "Asia/Shanghai") -> None:
        self._window_size = window_size
        self._timezone = ZoneInfo(timezone)
        self._windows: dict[str, deque[ConversationEntry]] = {}

    def format_timestamp(self, value: int | float | datetime | None = None) -> str:
        if isinstance(value, datetime):
            moment = value
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=self._timezone)
        elif value:
            timestamp = float(value)
            if abs(timestamp) >= 100_000_000_000:
                timestamp /= 1000
            moment = datetime.fromtimestamp(timestamp, tz=self._timezone)
        else:
            moment = datetime.now(tz=self._timezone)
        local = moment.astimezone(self._timezone)
        return f"{local:%Y-%m-%d} {_WEEKDAYS[local.weekday()]} {local:%H:%M}"

    @staticmethod
    def _key(chat_type: str, chat_id: str) -> str:
        return f"{chat_type}:{chat_id}"

    def window(self, chat_type: str, chat_id: str) -> deque[ConversationEntry]:
        key = self._key(chat_type, chat_id)
        return self._windows.setdefault(key, deque(maxlen=self._window_size))

    def add_user(
        self,
        chat_type: str,
        chat_id: str,
        text: str,
        speaker_id: str = "",
        speaker_name: str = "",
        quote: dict | None = None,
        timestamp: int | float | datetime | None = None,
    ) -> None:
        meta: dict = {
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "timestamp": self.format_timestamp(timestamp),
        }
        if quote is not None:
            meta["quote"] = quote
        self.window(chat_type, chat_id).append(("user", text, meta))

    def add_ai(
        self,
        chat_type: str,
        chat_id: str,
        text: str,
        timestamp: int | float | datetime | None = None,
    ) -> None:
        self.window(chat_type, chat_id).append(
            ("assistant", text, {"timestamp": self.format_timestamp(timestamp)})
        )

    def all_windows(self) -> tuple[tuple[str, deque[ConversationEntry]], ...]:
        return tuple(self._windows.items())
