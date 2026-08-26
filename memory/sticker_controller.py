from __future__ import annotations

from shared.contracts.rpc.rpc_model import SuccessResponse
from shared.contracts.rpc.sticker import (
    StickerAddRequest,
    StickerAddResponse,
    StickerBoostRequest,
    StickerSearchRequest,
    StickerSearchResponse,
)


class StickerController:
    def __init__(self, service) -> None:
        self._service = service

    async def add(self, request: StickerAddRequest) -> StickerAddResponse:
        result = await self._service.add(
            request.ai_id,
            request.model_dump(mode="python", exclude={"ai_id"}),
        )
        return StickerAddResponse.model_validate(result)

    async def search(self, request: StickerSearchRequest) -> StickerSearchResponse:
        sticker = await self._service.search(request.ai_id, request.query)
        return StickerSearchResponse.model_validate({"sticker": sticker})

    async def boost(self, request: StickerBoostRequest) -> SuccessResponse:
        await self._service.boost(request.ai_id, request.sticker_id)
        return SuccessResponse()
