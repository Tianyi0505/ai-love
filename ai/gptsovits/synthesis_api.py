from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, ConfigDict

from ai.gptsovits.synthesis_service import SynthesisService


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_id: str
    text: str


class SynthesizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_path: str
    duration_sec: float


def create_app(service: SynthesisService) -> FastAPI:
    router = APIRouter()

    @router.get("/healthz")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @router.post("/synthesize", response_model=SynthesizeResponse)
    async def synthesize(request: SynthesizeRequest) -> dict:
        return await service.synthesize(request.ai_id, request.text)

    app = FastAPI(title="ai-love GPT-SoVITS")
    app.include_router(router)
    return app
