import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agent.conversation.failover_chat_agent import FailoverChatAgent
from agent.conversation.multimodal_input import ImageAttachment
from agent.conversation.response_plan import Emotion, ParticipationDecision, ResponsePlan, Speech
from agent.vision.image_description import ImageDescription


def response_plan(text: str) -> ResponsePlan:
    return ResponsePlan(
        speech=[Speech(text=text, delivery="text")],
        emotion=Emotion(name="neutral", intensity=0.0),
        actions=[],
    )


class ModelFailoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_next_multimodal_model_is_tried_before_split_fallback(self) -> None:
        expected = response_plan("第二个一体模型成功")
        first = SimpleNamespace(generate_plan=AsyncMock(side_effect=RuntimeError("primary-1 down")))
        second = SimpleNamespace(generate_plan=AsyncMock(return_value=expected))
        fallback = SimpleNamespace(generate_plan=AsyncMock())
        vision = SimpleNamespace(describe=AsyncMock())
        router = FailoverChatAgent(
            primaries=(("vision-1", first), ("vision-2", second)),
            fallback=fallback,
            image_describer=vision,
            fallback_model_name="text-fallback",
        )
        images = (
            ImageAttachment(
                source_url="https://example.com/image.jpg",
                data_url="data:image/jpeg;base64,aW1hZ2U=",
                attribution="小爱: [图片]",
            ),
        )

        result = await router.generate_plan("system", "user", images=images)

        self.assertEqual(expected, result)
        first.generate_plan.assert_awaited_once()
        second.generate_plan.assert_awaited_once()
        fallback.generate_plan.assert_not_awaited()
        vision.describe.assert_not_awaited()

    async def test_split_models_are_used_after_all_multimodal_models_fail(self) -> None:
        expected = response_plan("分离模型成功")
        first = SimpleNamespace(generate_plan=AsyncMock(side_effect=RuntimeError("primary-1 down")))
        second = SimpleNamespace(generate_plan=AsyncMock(side_effect=RuntimeError("primary-2 down")))
        fallback = SimpleNamespace(generate_plan=AsyncMock(return_value=expected))
        vision = SimpleNamespace(
            describe=AsyncMock(
                return_value=ImageDescription(
                    description="一只白猫",
                    image_type="photo",
                    tags=["猫"],
                    match_quality=0.1,
                    emotion="neutral",
                    sticker_description="",
                )
            )
        )
        router = FailoverChatAgent(
            primaries=(("vision-1", first), ("vision-2", second)),
            fallback=fallback,
            image_describer=vision,
            fallback_model_name="text-fallback",
        )
        image = ImageAttachment(
            source_url="https://example.com/image.jpg",
            data_url="data:image/jpeg;base64,aW1hZ2U=",
            attribution="小爱: [图片]",
        )

        result = await router.generate_plan("system", "user", images=(image,))

        self.assertEqual(expected, result)
        first.generate_plan.assert_awaited_once()
        second.generate_plan.assert_awaited_once()
        vision.describe.assert_awaited_once_with(image.source_url)
        fallback.generate_plan.assert_awaited_once()
        fallback_user_prompt = fallback.generate_plan.await_args.args[1]
        self.assertIn("小爱: [图片] 一只白猫", fallback_user_prompt)

    async def test_participation_uses_split_models_only_after_primary_group_fails(self) -> None:
        decision = ParticipationDecision(participate=True, reason="图片里在问我")
        first = SimpleNamespace(decide_participation=AsyncMock(side_effect=RuntimeError("primary-1 down")))
        second = SimpleNamespace(decide_participation=AsyncMock(side_effect=RuntimeError("primary-2 down")))
        fallback = SimpleNamespace(decide_participation=AsyncMock(return_value=decision))
        vision = SimpleNamespace(
            describe=AsyncMock(
                return_value=ImageDescription(
                    description="图片中的人正在提问",
                    image_type="photo",
                    tags=["提问"],
                    match_quality=0.0,
                    emotion="neutral",
                    sticker_description="",
                )
            )
        )
        router = FailoverChatAgent(
            primaries=(("vision-1", first), ("vision-2", second)),
            fallback=fallback,
            image_describer=vision,
            fallback_model_name="text-fallback",
        )
        image = ImageAttachment(
            source_url="https://example.com/question.jpg",
            data_url="data:image/jpeg;base64,cXVlc3Rpb24=",
            attribution="小博: [图片]",
        )

        result = await router.decide_participation("system", "user", images=(image,))

        self.assertEqual(decision, result)
        first.decide_participation.assert_awaited_once()
        second.decide_participation.assert_awaited_once()
        fallback.decide_participation.assert_awaited_once()
        fallback_user_prompt = fallback.decide_participation.await_args.args[1]
        self.assertIn("小博: [图片] 图片中的人正在提问", fallback_user_prompt)


if __name__ == "__main__":
    unittest.main()
