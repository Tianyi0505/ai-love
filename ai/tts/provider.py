
from __future__ import annotations

from abc import ABC, abstractmethod

from ai.tts.types import AudioResult, SynthesizeRequest
# 定义语音合成服务接口
class TTSProvider(ABC):

    # 合成语音内容
    async def synthesize(self, req: SynthesizeRequest) -> AudioResult:
        text = await self._preprocess(req.text, req)
        result = await self._do_synthesize(req, text)
        result = await self._postprocess(result, req)
        return result

    # 关闭资源
    async def close(self) -> None:
        pass

    # 执行语音合成请求
    @abstractmethod
    async def _do_synthesize(self, req: SynthesizeRequest, text: str) -> AudioResult:
        pass

    # 准备模型输入
    async def _preprocess(self, text: str, req: SynthesizeRequest) -> str:
        return text

    # 整理模型输出
    async def _postprocess(self, result: AudioResult, req: SynthesizeRequest) -> AudioResult:
        return result
