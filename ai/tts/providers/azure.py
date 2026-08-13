
from __future__ import annotations

from ai.tts.provider import TTSProvider
from ai.tts.registry import provider_registry
from ai.tts.types import AudioResult, SynthesizeRequest
from shared.infrastructure.runtime_config import ConfigKey, required_setting


# 提供Azure语音合成能力
@provider_registry.register("azure")
class AzureTTSProvider(TTSProvider):
    # 初始化当前实例
    def __init__(self, refs: dict[str, str], key: str | None = None, region: str | None = None, **_) -> None:
        self._key = required_setting(key, ConfigKey.AZURE_SPEECH_KEY)
        self._region = required_setting(region, ConfigKey.AZURE_SPEECH_REGION)
        self._voices = refs

    # 执行语音合成请求
    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        # 使用 Azure Speech SDK 合成语音
        raise NotImplementedError(
            f"Azure 引擎待实现: voice={self._voices.get(req.ai_id, '未配置')}"
        )
