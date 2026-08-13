from __future__ import annotations

import unittest

from agent.application.proactive import ProactiveChat


# 验证主动私聊筛选规则
class ProactiveChatTests(unittest.IsolatedAsyncioTestCase):

    # 准备测试环境
    def setUp(self) -> None:
        self.chat = ProactiveChat({
            "proactive": {
                "timezone": "Asia/Shanghai",
                "work_hours": [{"start": "00:00", "end": "23:59"}],
                "private_quiet_period_sec": 0,
            }
        })

    # 验证无合适内容时不主动发言
    async def test_does_not_initiate_without_something_to_say(self) -> None:
        candidates = await self.chat.run_private(
            [{"user_id": "1", "familiarity": 1.0, "importance": 0.0}],
            min_w=0.1,
        )

        self.assertEqual(candidates, [])

    # 验证存在明确理由时主动发言
    async def test_initiates_with_concrete_reason(self) -> None:
        candidates = await self.chat.run_private(
            [{
                "user_id": "1",
                "familiarity": 1.0,
                "importance": 0.0,
                "reason": "想分享刚发现的一首歌",
            }],
            min_w=0.1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["reason"], "想分享刚发现的一首歌")
