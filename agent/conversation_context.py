from __future__ import annotations

from collections import deque

ConversationEntry = tuple[str, str, dict]


def format_entries(entries, ai_name: str = "") -> str:
    blocks: list[str] = []
    for role, text, meta in entries:
        if role == "assistant":
            blocks.append(f"[AI | {ai_name}]\n{text}" if ai_name else f"[AI]\n{text}")
            continue
        name = str(meta["speaker_name"])
        person_id = str(meta["speaker_id"])
        label = f"[{person_id} | {name}]" if person_id else f"[{name}]"
        quote = meta.get("quote")
        if quote is not None:
            blocks.append(f"{label}\n[引用 {quote['name']}]\n{text}")
        else:
            blocks.append(f"{label}\n{text}")
    return "\n\n".join(blocks)


class ConversationContext:
    def __init__(self, window_size: int) -> None:
        self._window_size = window_size
        self._windows: dict[str, deque[ConversationEntry]] = {}

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
    ) -> None:
        meta: dict = {"speaker_id": speaker_id, "speaker_name": speaker_name}
        if quote is not None:
            meta["quote"] = quote
        self.window(chat_type, chat_id).append(("user", text, meta))

    def add_ai(self, chat_type: str, chat_id: str, text: str) -> None:
        self.window(chat_type, chat_id).append(("assistant", text, {}))

    def all_windows(self) -> tuple[tuple[str, deque[ConversationEntry]], ...]:
        return tuple(self._windows.items())
