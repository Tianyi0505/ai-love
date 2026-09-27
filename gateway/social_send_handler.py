from __future__ import annotations

import asyncio
import logging

from shared import private_reply_observability as private_metrics
from shared.contracts.rpc.social import (
    DeliveryRejected,
    DeliveryRetryable,
    DeliveryUnknown,
    ReplyUnavailable,
    SocialSendRequest,
    SocialSendResponse,
    SocialSendStatusResponse,
)

logger = logging.getLogger('ailove.gateway.delivery')


class SocialSendHandler:
    def __init__(self, channels, conversations, deliveries, ownership, *, send_retries=2):
        self._channels = channels
        self._conversations = conversations
        self._deliveries = deliveries
        self._ownership = ownership
        self._send_retries = send_retries

    async def _authorize(self, request):
        if await self._ownership.owner_for(request.account_id) != request.ai_id:
            raise DeliveryRejected('账号不属于当前AI')

    async def status(self, request):
        await self._authorize(request)
        row = await self._deliveries.get(request.ai_id, request.account_id, request.run_id)
        if row is None:
            return SocialSendStatusResponse(status='not_found')
        return SocialSendStatusResponse(status=row.status, message_id=row.platform_message_id,
            reason_code=row.reason_code, retryable=row.status == 'failed' and row.reason_code == 'DeliveryRetryable')

    async def send(self, request: SocialSendRequest) -> SocialSendResponse:
        await self._authorize(request)
        channel = self._channels[request.account_id]
        if request.chat.chat_type.value != 'private':
            response = await channel.send(request)
            await self._conversations.record_outbound(request, response, request.ai_id)
            return response
        if not request.delivery_kind or not request.person_id:
            raise DeliveryRejected('私聊发送必须有持久来源')
        for attempt in range(self._send_retries + 1):
            row = await self._deliveries.begin(request)
            if row.status == 'sent':
                return SocialSendResponse(message_id=row.platform_message_id)
            wire_request = SocialSendRequest.model_validate(row.request_snapshot)
            try:
                try:
                    response = await channel.send(wire_request)
                except ReplyUnavailable:
                    wire_request = SocialSendRequest.model_validate(await self._deliveries.without_quote(request))
                    response = await channel.send(wire_request)
            except DeliveryRetryable:
                if row.attempt_count >= self._send_retries + 1:
                    await self._deliveries.complete(request, 'failed', reason='retry_exhausted')
                    private_metrics.delivery('failed', 'retry_exhausted')
                    raise DeliveryRejected('明确未发送，恢复预算耗尽') from None
                await self._deliveries.complete(request, 'failed', reason='DeliveryRetryable')
                await asyncio.sleep((5, 15)[min(attempt, 1)])
                continue
            except DeliveryRejected as exc:
                await self._deliveries.complete(request, 'failed', reason=type(exc).__name__)
                private_metrics.delivery('failed', type(exc).__name__)
                raise
            except asyncio.CancelledError:
                # 发送已开始，取消不证明未送达；恢复扫描保留unknown。
                raise
            except Exception as exc:
                await self._deliveries.complete(request, 'unknown', reason=type(exc).__name__)
                private_metrics.delivery('unknown', type(exc).__name__)
                raise DeliveryUnknown('平台发送结果未知') from exc
            # 先提交权威确认。数据库提交失败时不能再发送。
            await self._deliveries.complete(request, 'sent', message_id=response.message_id)
            private_metrics.delivery('sent')
            await self._record_history(wire_request, response)
            return response
        raise DeliveryRejected('发送预算耗尽')

    async def _record_history(self, request, response):
        try:
            await self._conversations.record_outbound(request, response, request.ai_id)
            await self._deliveries.history_done(request)
        except Exception:
            logger.warning('history_pending run_id=%s', request.run_id)

    async def recover(self):
        for row in await self._deliveries.unsettled():
            request = SocialSendRequest.model_validate(row.request_snapshot)
            if row.status == 'sent':
                await self._record_history(request, SocialSendResponse(message_id=row.platform_message_id))
            else:
                await self._deliveries.complete(request, 'unknown', reason='confirmation_lost')
                logger.error('delivery_unknown run_id=%s ai_id=%s', row.run_id, row.ai_id)
