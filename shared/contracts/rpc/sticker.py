from __future__ import annotations

from datetime import datetime

from shared.contracts.rpc.rpc_model import RpcModel, SuccessResponse


class StickerRecord(RpcModel):
    id: str
    image_url: str
    description: str
    tags: list[str]
    match_quality: float
    usage_strength: float
    boost_count: int
    created_at: datetime
    last_used_at: datetime | None
    freshness: float
    retention_score: float


class StickerSearchRequest(RpcModel):
    ai_id: str
    query: str


class StickerSearchResponse(RpcModel):
    sticker: StickerRecord | None


class StickerAddRequest(RpcModel):
    ai_id: str
    id: str
    image_url: str
    description: str
    tags: list[str]
    match_quality: float


class StickerAddResponse(SuccessResponse):
    action: str
    evicted: str | None = None


class StickerBoostRequest(RpcModel):
    ai_id: str
    sticker_id: str
