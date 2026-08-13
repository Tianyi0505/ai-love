from __future__ import annotations

import unittest

from agent.application.proactive import ProactiveChat


class ProactiveChatTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.chat = ProactiveChat({
            "proactive": {
                "timezone": "Asia/Shanghai",
                "work_hours": [{"start": "00:00", "end": "23:59"}],
                "private_quiet_period_sec": 0,
            }
        })

    async def test_does_not_initiate_without_something_to_say(self) -> None:
        candidates = await self.chat.run_private(
            [{"user_id": "1", "familiarity": 1.0, "importance": 0.0}],
            min_w=0.1,
        )

        self.assertEqual(candidates, [])

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
