from __future__ import annotations

import asyncio
import json
import logging

from ai.llm.types import ChatMessage, ChatRequest

logger = logging.getLogger("ailove.agent.memory_consolidation")


class MemoryConsolidator:

    def __init__(self, memory, llm, ai_id: str, gcfg, prompts) -> None:
        self._memory = memory
        self._llm = llm
        self._ai_id = ai_id
        self._gcfg = gcfg
        self._prompts = prompts
        self._config = gcfg.section("memory")

    async def consolidate_loop(self, windows_getter) -> None:
        interval = int(self._gcfg.get("social", "consolidate_interval_sec"))
        threshold = float(self._gcfg.get("social", "consolidate_threshold"))
        window_size = int(self._gcfg.get("social", "window_size"))
        while True:
            await asyncio.sleep(interval)
            for chat_key, window in windows_getter():
                if len(window) >= window_size * threshold:
                    logger.info("[memory] 压缩: %s 窗口 %s/%s", chat_key, len(window), window_size)
                    await self.compress_window(chat_key, window)

    async def compress_window(self, chat_key: str, window) -> None:
        retained = int(self._config["retained_window_messages"])
        history_text = "\n".join(f"{role}: {content}" for role, content in list(window)[:-retained])
        if not history_text.strip():
            return
        participants = self._participants(history_text)
        if not participants:
            logger.info("[memory] 窗口尚无可归属的说话人身份，暂不压缩: %s", chat_key)
            return
        participant_text = json.dumps(list(participants.values()), ensure_ascii=False)
        prompt = self._prompts.render(
            "memory-consolidation",
            participants=participant_text,
            history=history_text,
        )
        try:
            parts: list[str] = []
            async for chunk in self._llm.chat(
                ChatRequest(ai_id=self._ai_id, messages=[ChatMessage(role="user", content=prompt)])
            ):
                if chunk.content:
                    parts.append(chunk.content)
            text = "".join(parts).strip()
        except Exception as e:
            logger.warning("记忆压缩失败: %s", e)
            return
        entries = []
        try:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
                for memory in parsed.get("memories", []):
                    content = str(memory.get("content", "")).strip()
                    if not content:
                        continue
                    person_id = str(memory.get("person_id") or "")
                    if person_id not in participants:
                        person_id = next(iter(participants)) if len(participants) == 1 else ""
                    if not person_id and self._uses_generic_person(content):
                        logger.warning("[memory] 跳过无法确定人物归属的群聊记忆: %s", content[:50])
                        continue
                    source = {"chat_key": chat_key}
                    if person_id:
                        participant = participants[person_id]
                        content = self._name_person(content, participant)
                        source.update(
                            {
                                "platform_user_id": participant["platform_user_id"],
                                "display_name": participant["display_name"],
                            }
                        )
                    entries.append(
                        {
                            "content": content,
                            "person_id": person_id or None,
                            "memory_type": memory.get("memory_type", "observation"),
                            "scope": "private",
                            "importance": float(memory.get("importance", self._config["default_importance"])),
                            "strength": float(self._config["default_strength"]),
                            "confidence": float(memory.get("confidence", self._config["default_confidence"])),
                            "emotion_intensity": float(memory.get("emotion_intensity", self._config["default_emotion_intensity"])),
                            "protected": bool(
                                memory.get("protected", False)
                                or memory.get("memory_type") == "commitment"
                            ),
                            "consolidated": True,
                            "source": source,
                        }
                    )
        except Exception:
            logger.exception("[memory] 解析压缩结果失败")
        if entries:
            try:
                await self._memory.write(entries)
                logger.info("记忆压缩写入 %s 条: %s", len(entries), text[:50])
            except Exception as e:
                logger.warning("记忆压缩写入失败: %s", e)
        while len(window) > retained:
            window.popleft()

    @staticmethod
    def _participants(history_text: str) -> dict[str, dict[str, str]]:
        participants = {}
        for line in history_text.splitlines():
            marker = "[speaker] "
            if marker not in line:
                continue
            try:
                speaker = json.loads(line.split(marker, 1)[1])
            except (json.JSONDecodeError, TypeError):
                continue
            person_id = str(speaker.get("person_id") or "")
            if not person_id:
                continue
            participants[person_id] = {
                "person_id": person_id,
                "platform_user_id": str(speaker.get("platform_user_id") or ""),
                "display_name": str(speaker.get("display_name") or ""),
            }
        return participants

    def _uses_generic_person(self, content: str) -> bool:
        return any(word in content for word in self._config["generic_person_terms"])

    def _name_person(self, content: str, participant: dict[str, str]) -> str:
        name = participant.get("display_name") or participant.get("platform_user_id") or ""
        if not name:
            return content
        for generic in self._config["generic_person_terms"]:
            for labeled_name in (
                f"{generic}{name}",
                f"{generic}（{name}）",
                f"{generic}“{name}”",
                f'{generic}"{name}"',
            ):
                content = content.replace(labeled_name, name)
            content = content.replace(generic, name)
        return content
