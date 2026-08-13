from __future__ import annotations

import logging

logger = logging.getLogger("ailove.agent.clients.tts")


class TTSClient:
    def __init__(self, bus, ai_id: str, timeouts: dict) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._timeouts = timeouts

    async def synthesize(self, text: str) -> dict | None:
        try:
            response = await self._bus.request_json(
                "tts.synthesize.request",
                {"ai_id": self._ai_id, "text": text},
                timeout=float(self._timeouts["tts_request_sec"]),
            )
            if response.get("ok"):
                return {
                    "audio_path": response["audio_path"],
                    "duration_sec": response["duration_sec"],
                }
        except Exception as exc:
            logger.warning("[agent:%s] 语音合成失败: %s", self._ai_id, exc)
        return None
