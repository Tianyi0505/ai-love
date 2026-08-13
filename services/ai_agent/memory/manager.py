from __future__ import annotations

import asyncio
import json
import logging

from services.ai_agent.llm.service import ChatMessage, ChatRequest

logger = logging.getLogger("ailove.ai-agent.memory")


class MemoryManager:

    def __init__(self, bus, llm, ai_id: str, gcfg) -> None:
        self._bus = bus
        self._llm = llm
        self._ai_id = ai_id
        self._gcfg = gcfg

    async def consolidate_loop(self, windows_getter) -> None:
        interval = int(self._gcfg.get("social", "consolidate_interval_sec", 600))
        threshold = float(self._gcfg.get("social", "consolidate_threshold", 0.6))
        window_size = int(self._gcfg.get("social", "window_size", 20))
        while True:
            await asyncio.sleep(interval)
            for chat_key, window in windows_getter():
                if len(window) >= window_size * threshold:
                    logger.info("[memory] 压缩: %s 窗口 %s/%s", chat_key, len(window), window_size)
                    await self.compress_window(chat_key, window)

    async def compress_window(self, chat_key: str, window) -> None:
        history_text = "\n".join(f"{role}: {content}" for role, content in list(window)[:-2])
        if not history_text.strip():
            return
        participants = self._participants(history_text)
        if not participants:
            logger.info("[memory] 窗口尚无可归属的说话人身份，暂不压缩: %s", chat_key)
            return
        participant_text = json.dumps(list(participants.values()), ensure_ascii=False)
        prompt = f"""请从以下对话中提取少量值得长期保留的记忆。寒暄和重复内容不要写入。

记忆类型只能是 observation、fact、belief、feeling、episodic、procedural、commitment。
- observation：实际听到或看到的内容
- fact：经过确认的事实
- belief：当前理解或判断，可能被修正
- feeling：主观感受
- commitment：未完成约定，默认保护

说话人清单（person_id 必须原样使用，不能编造）：
{participant_text}

人物相关记忆必须：
1. 写明它与谁有关，每条只绑定一个 person_id；涉及多人时拆成多条。
2. content 使用清单中的具体昵称（无昵称时用 platform_user_id），禁止统称“用户”或“对方”。
3. 只有与任何人物都无关的全局事实，person_id 才能为 null。

对话：
{history_text}

只输出 JSON：
{{"memories":[{{"content":"内容","person_id":"说话人清单中的 UUID 或 null","memory_type":"fact","importance":0.0,"confidence":0.0,"emotion_intensity":0.0,"protected":false}}]}}
所有数值范围 0.0-1.0；无内容时输出 {{"memories":[]}}。"""
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
                            "importance": float(memory.get("importance", 0.5)),
                            "strength": 0.6,
                            "confidence": float(memory.get("confidence", 0.7)),
                            "emotion_intensity": float(memory.get("emotion_intensity", 0.0)),
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
                await self._bus.request_json(
                    "memory.write.request",
                    {"ai_id": self._ai_id, "entries": entries},
                    timeout=5.0,
                )
                logger.info("记忆压缩写入 %s 条: %s", len(entries), text[:50])
            except Exception as e:
                logger.warning("记忆压缩写入失败: %s", e)
        while len(window) > 2:
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

    @staticmethod
    def _uses_generic_person(content: str) -> bool:
        return any(word in content for word in ("用户", "对方", "该用户"))

    @staticmethod
    def _name_person(content: str, participant: dict[str, str]) -> str:
        name = participant.get("display_name") or participant.get("platform_user_id") or ""
        if not name:
            return content
        for generic in ("该用户", "用户", "对方"):
            for labeled_name in (
                f"{generic}{name}",
                f"{generic}（{name}）",
                f"{generic}“{name}”",
                f'{generic}"{name}"',
            ):
                content = content.replace(labeled_name, name)
            content = content.replace(generic, name)
        return content

    async def vector_search(self, query: str, top_k: int = 5, person_id: str = "") -> list[str]:
        try:
            resp = await self._bus.request_json(
                "memory.search.request",
                {
                    "ai_id": self._ai_id,
                    "query": query,
                    "top_k": top_k,
                    "person_id": person_id,
                },
                timeout=2.0,
            )
            return [r.get("content", "") for r in resp.get("results", []) if r.get("content")]
        except Exception:
            return []
