from __future__ import annotations

from gateway.channel import Channel
from shared.contracts.rpc.social import SocialSendRequest, SocialSendResponse
from shared.conversation_repository import ConversationRepository


class SocialSendHandler:
    def __init__(
        self,
        channels: dict[str, Channel],
        conversations: ConversationRepository,
    ) -> None:
        self._channels = channels
        self._conversations = conversations

    async def send(self, request: SocialSendRequest) -> SocialSendResponse:
        channel = self._channels[request.account_id]
        response = await channel.send(request)
        await self._conversations.record_outbound(request, response, request.ai_id)
        return response
