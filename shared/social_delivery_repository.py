"""平台发送记录：只对已证明未发送的失败重试。"""
import hashlib
import json
from datetime import timedelta

from sqlalchemy import select, update

from shared import database_models as m
from shared.contracts.rpc.social import (
    DeliveryConflict,
    DeliveryInProgress,
    DeliveryRejected,
    DeliveryUnknown,
    StaleClaim,
)
from shared.private_interaction_repository import PrivateInteractionRepository, utcnow


def digest(payload):
    content = {key: value for key, value in payload.items() if key != 'claim_version'}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class SocialDeliveryRepository:
    def __init__(self, db, *, clock=utcnow):
        self.db = db
        self.clock = clock
        self.interactions = PrivateInteractionRepository(db, clock=clock)

    async def get(self, ai_id, account_id, run_id):
        async with self.db.session() as session:
            return await session.get(m.SocialDelivery, (ai_id, account_id, run_id))

    async def begin(self, request):
        payload = request.model_dump(mode='json')
        checksum = digest(payload)
        now = self.clock()
        async with self.db.session() as session, session.begin():
            state = await self.interactions.contact(session, request.ai_id, request.person_id)
            job = None
            if request.delivery_kind == 'private_reply':
                job = (await session.execute(select(m.PrivateReplyJob).where(
                    m.PrivateReplyJob.job_id == int(request.source_job_id)
                ).with_for_update())).scalar_one_or_none()
                if job is None or (job.ai_id, job.account_id, job.person_id, job.run_id) != (
                        request.ai_id, request.account_id, int(request.person_id), request.run_id):
                    raise StaleClaim('发送不属于当前私信')
            elif request.delivery_kind != 'proactive_private':
                raise DeliveryRejected('未知私聊发送类型')
            key = (request.ai_id, request.account_id, request.run_id)
            delivery = (await session.execute(select(m.SocialDelivery).filter_by(
                ai_id=key[0], account_id=key[1], run_id=key[2]).with_for_update())).scalar_one_or_none()
            if delivery is not None:
                if checksum not in (delivery.request_digest, delivery.original_digest):
                    raise DeliveryConflict('相同发送键不允许修改内容或目标')
                if delivery.status == 'sent':
                    return delivery
                if delivery.status == 'unknown':
                    raise DeliveryUnknown(delivery.reason_code)
                if delivery.status == 'sending':
                    raise DeliveryInProgress('发送尚未确认')
                if delivery.status == 'failed' and delivery.reason_code != 'DeliveryRetryable':
                    raise DeliveryRejected(delivery.reason_code)
            if job is not None:
                if (job.claim_version != request.claim_version or job.status != 'prepared'
                        or job.lease_until is None or job.lease_until <= now):
                    raise StaleClaim('任务领取已失效')
                if not job.response_snapshot or digest(job.response_snapshot) != checksum:
                    raise DeliveryConflict('发送内容与已准备回复不同')
            else:
                if (state.status != 'active' or state.pending_run_id != request.run_id
                        or state.pending_revision != state.revision or state.unanswered_count >= 3):
                    raise StaleClaim('主动联系预占已失效')
                identity = await session.scalar(select(m.PlatformIdentity.identity_id).where(
                    m.PlatformIdentity.person_id == int(request.person_id),
                    m.PlatformIdentity.account_id == request.account_id,
                    m.PlatformIdentity.platform == request.channel,
                    m.PlatformIdentity.platform_user_id == request.chat.chat_id))
                if identity is None:
                    raise DeliveryRejected('主动目标不属于可信联系人身份')
            if delivery is None:
                delivery = m.SocialDelivery(ai_id=key[0], account_id=key[1], run_id=key[2],
                    kind=request.delivery_kind, person_id=int(request.person_id),
                    conversation_id=request.conversation_id,
                    source_job_id=int(request.source_job_id) if request.source_job_id else None,
                    claim_version=request.claim_version, request_snapshot=payload,
                    request_digest=checksum, original_digest=checksum, status='prepared',
                    attempt_count=0, revision=0, created_at=now, updated_at=now)
                session.add(delivery)
            delivery.status = 'sending'
            delivery.attempt_count += 1
            delivery.updated_at = now
            await session.flush()
            return delivery

    async def complete(self, request, status, *, message_id='', reason=''):
        now = self.clock()
        async with self.db.session() as session, session.begin():
            state = await self.interactions.contact(session, request.ai_id, request.person_id)
            job = None
            if request.source_job_id:
                job = (await session.execute(select(m.PrivateReplyJob).where(
                    m.PrivateReplyJob.job_id == int(request.source_job_id)).with_for_update())).scalar_one_or_none()
            delivery = (await session.execute(select(m.SocialDelivery).filter_by(
                ai_id=request.ai_id, account_id=request.account_id, run_id=request.run_id
            ).with_for_update())).scalar_one()
            if delivery.status == 'sent':
                return
            delivery.status, delivery.platform_message_id, delivery.reason_code = status, message_id, reason
            delivery.updated_at = now
            if job is not None and status in ('sent', 'unknown'):
                job.status, job.reason_code, job.updated_at = status, reason, now
                job.lease_until = None
            if request.delivery_kind == 'proactive_private' and state.pending_run_id == request.run_id:
                if status == 'unknown' or (status == 'sent' and state.revision != state.pending_revision):
                    state.status, state.reason_code = 'unknown', reason or 'inbound_during_send'
                elif status == 'sent':
                    state.unanswered_count += 1
                    state.last_success_at = now
                    state.pending_run_id = None
                    state.pending_revision = None
                    state.status = 'active'
                    state.reason_code = ''
                elif status == 'failed' and reason != 'DeliveryRetryable':
                    state.pending_run_id = None
                    state.pending_revision = None
                    state.status = 'active'
                    state.reason_code = reason
                state.updated_at = now

    async def without_quote(self, request):
        async with self.db.session() as session, session.begin():
            row = (await session.execute(select(m.SocialDelivery).filter_by(
                ai_id=request.ai_id, account_id=request.account_id, run_id=request.run_id
            ).with_for_update())).scalar_one()
            if row.status != 'sending' or row.revision or not request.reply_to_message_id:
                raise DeliveryRejected('不允许再次修改引用')
            snapshot = dict(row.request_snapshot)
            snapshot['reply_to_message_id'] = ''
            row.request_snapshot, row.request_digest = snapshot, digest(snapshot)
            row.revision = 1
            row.reason_code = 'quote_removed'
            return snapshot

    async def history_done(self, request):
        async with self.db.session() as session, session.begin():
            await session.execute(update(m.SocialDelivery).filter_by(
                ai_id=request.ai_id, account_id=request.account_id, run_id=request.run_id
            ).values(history_recorded=True))

    async def unsettled(self, limit=100):
        async with self.db.session() as session:
            return list((await session.scalars(select(m.SocialDelivery).where(
                ((m.SocialDelivery.status == 'sent') & ~m.SocialDelivery.history_recorded)
                | ((m.SocialDelivery.status == 'sending') &
                   (m.SocialDelivery.updated_at < self.clock() - timedelta(seconds=60)))
            ).order_by(m.SocialDelivery.updated_at).limit(limit))).all())

    async def cleanup(self, retention_days=180):
        async with self.db.session() as session, session.begin():
            await session.execute(update(m.SocialDelivery).where(
                m.SocialDelivery.status.in_(('sent', 'failed')), m.SocialDelivery.history_recorded,
                m.SocialDelivery.updated_at < self.clock() - timedelta(days=retention_days),
            ).values(request_snapshot={}))
