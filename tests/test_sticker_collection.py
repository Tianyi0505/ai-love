from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import AssistantMsg
from output_fixtures import ResultModel, ValidatingOutputClient

from agent.social.sticker_collector import StickerCollector
from agent.social.sticker_judge import StickerJudge
from agent.vision.image_describer import ImageDescriber
from agent.vision.image_description import ImageDescription
from agent.vision.image_fetcher import FetchedImage
from agent.vision.vision_output_policy import VisionOutputPolicy
from shared.global_settings import GlobalSettings
from tests.test_group_message_json import FileConfigProvider


@pytest.mark.parametrize("image_type", ["sticker", "screenshot", "photo", "illustration", "other"])
async def test_collection_requires_sticker_classification_even_with_high_score(image_type):
    """验证收集链路依据明确分类选择表情素材"""
    config = await FileConfigProvider().get("ailove.config")
    config["qq"]["whitelist"] = []
    settings = GlobalSettings.model_validate(config)
    output = ImageDescription(
        description="图片中出现开心和鼓掌的内容", image_type=image_type,
        tags=["开心", "鼓掌"], match_quality=0.95, emotion="happy", sticker_description="开心鼓掌",
    )
    call = AsyncMock(return_value={"parsed": output, "raw": AssistantMsg("model", content=""), "parsing_error": None})
    model = ResultModel(call)
    fetcher = SimpleNamespace(fetch=AsyncMock(return_value=FetchedImage(data=b"image", media_type="image/png")))
    vision = ImageDescriber(
        model, "vision", fetcher, VisionOutputPolicy(settings.image.output_limits),
        settings.image.prompt, 100, 0, settings.observability, ValidatingOutputClient(),
    )
    stickers = SimpleNamespace(add=AsyncMock(return_value=True))
    collector = StickerCollector("ai-test", vision, stickers, settings.sticker.collect_min_quality)

    await collector.collect(["https://example.com/candidate.png"])

    call.assert_awaited_once()
    if image_type == "sticker":
        stickers.add.assert_awaited_once_with("https://example.com/candidate.png", "开心鼓掌", ["开心", "鼓掌"], 0.95)
    else:
        stickers.add.assert_not_awaited()


@pytest.mark.parametrize("failure", ["fetch", "model"])
async def test_unavailable_sticker_evaluation_keeps_text_reply(failure):
    """验证图片或判断模型不可用时采用文字回复"""
    fetcher = SimpleNamespace(data_urls=AsyncMock(return_value=("data:image/png;base64,YQ==",)))
    call = AsyncMock(side_effect=RuntimeError("判断服务不可用"))
    model = ResultModel(call)
    if failure == "fetch":
        fetcher.data_urls.side_effect = RuntimeError("图片获取失败")
    judge = StickerJudge(
        model, "vision", fetcher, "结合图片判断", 100, 0,
        SimpleNamespace(include_model_content=False, include_binary_content=False, include_model_request_parameters=False),
        ValidatingOutputClient(),
    )

    assert not await judge.should_send("https://example.com/candidate.png", {"计划回复": "我陪着你"})
