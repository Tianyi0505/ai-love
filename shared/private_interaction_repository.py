"""私聊任务和主动状态的唯一持久入口。锁顺序：联系人 → 任务 → 发送。"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from shared import database_models as m
from shared.contracts.rpc.social import StaleClaim
from shared.snowflake_id_generator import snowflake_ids


def utcnow():
    return datetime.now(timezone.utc)


class PrivateInteractionRepository:
    def __init__(self, db, *, retention_days=180, clock=utcnow):
        self.db = db
        self.retention_days = retention_days
        self.clock = clock

    async def contact(self, session, ai_id, person_id):
        await session.execute(insert(m.PrivateContactState).values(ai_id=ai_id, person_id=int(person_id))
                              .on_conflict_do_nothing())
        return (await session.execute(select(m.PrivateContactState).where(
            m.PrivateContactState.ai_id == ai_id, m.PrivateContactState.person_id == int(person_id)
        ).with_for_update())).scalar_one()

    async def accept(self, message, ai_id):
        now = self.clock()
        async with self.db.session() as session, session.begin():
            # 插入冲突不修改首次AI归属，也不会重置状态。
            job_id = snowflake_ids().next_id()
            criteria = dict(platform=message.platform, account_id=message.account_id,
                            conversation_id=int(message.meta['conversation_id']),
                            platform_message_id=message.message_id)
            result = await session.execute(insert(m.PrivateReplyJob).values(
                job_id=job_id, ai_id=ai_id, person_id=int(message.meta['person_id']),
                run_id=str(job_id), message_snapshot=message.model_dump(mode='json'),
                retain_until=now + timedelta(days=self.retention_days), created_at=now, updated_at=now,
                **criteria).on_conflict_do_nothing().returning(m.PrivateReplyJob.job_id))
            fresh = result.scalar_one_or_none() is not None
            job = (await session.execute(select(m.PrivateReplyJob).filter_by(**criteria))).scalar_one()
            if fresh:
                state = await self.contact(session, ai_id, job.person_id)
                state.unanswered_count = 0
                state.last_inbound_job_id = job.job_id
                state.last_inbound_at = now
                state.revision += 1
                state.updated_at = now
                if state.pending_run_id:
                    delivery = (await session.execute(select(m.SocialDelivery).where(
                        m.SocialDelivery.ai_id == ai_id, m.SocialDelivery.run_id == state.pending_run_id
                    ).with_for_update())).scalar_one_or_none()
                    if delivery is not None and delivery.status in ('sending', 'unknown'):
                        state.status, state.reason_code = 'unknown', 'inbound_during_send'
                    else:
                        if delivery is not None and delivery.status == 'prepared':
                            delivery.status, delivery.reason_code = 'failed', 'StaleClaim'
                        state.pending_run_id = None
                        state.pending_revision = None
                        state.status, state.reason_code = 'active', ''
                elif state.status != 'unknown':
                    state.status, state.reason_code = 'active', ''
            return job, fresh

    async def ready(self, job_id, message):
        async with self.db.session() as session, session.begin():
            await session.execute(update(m.PrivateReplyJob).where(
                m.PrivateReplyJob.job_id == int(job_id), m.PrivateReplyJob.status == 'accepted'
            ).values(message_snapshot=message.model_dump(mode='json'), status='ready', updated_at=self.clock()))

    async def pending(self, statuses, limit=100, ai_id=None):
        async with self.db.session() as session:
            query = select(m.PrivateReplyJob).where(m.PrivateReplyJob.status.in_(statuses))
            if ai_id is not None:
                query = query.where(m.PrivateReplyJob.ai_id == ai_id)
            return list((await session.scalars(query.order_by(m.PrivateReplyJob.received_seq).limit(limit))).all())

    async def claim(self, job_id, ai_id, lease_sec=120):
        now = self.clock()
        async with self.db.session() as session, session.begin():
            job = (await session.execute(select(m.PrivateReplyJob).where(
                m.PrivateReplyJob.job_id == int(job_id), m.PrivateReplyJob.ai_id == ai_id
            ).with_for_update())).scalar_one_or_none()
            if job is None or job.status in ('accepted', 'sent', 'failed', 'unknown'):
                return None
            older = aliased(m.PrivateReplyJob)
            if await session.scalar(select(exists().where(
                older.conversation_id == job.conversation_id, older.received_seq < job.received_seq,
                older.status.in_(('accepted', 'ready', 'processing', 'prepared'))))):
                return None
            if job.lease_until and job.lease_until > now:
                return None
            interrupted = job.status == 'processing'
            job.claim_version += 1
            job.lease_until = now + timedelta(seconds=lease_sec)
            if job.response_snapshot is None:
                job.status = 'processing'
            job.reason_code = 'interrupted' if interrupted else job.reason_code
            job.updated_at = now
            return job

    async def heartbeat(self, job_id, version, lease_sec):
        async with self.db.session() as session, session.begin():
            result = await session.execute(update(m.PrivateReplyJob).where(
                m.PrivateReplyJob.job_id == int(job_id), m.PrivateReplyJob.claim_version == version,
                m.PrivateReplyJob.status.in_(('processing', 'prepared')),
            ).values(lease_until=self.clock() + timedelta(seconds=lease_sec)))
            return result.rowcount == 1

    async def prepare(self, job_id, version, command):
        async with self.db.session() as session, session.begin():
            result = await session.execute(update(m.PrivateReplyJob).where(
                m.PrivateReplyJob.job_id == int(job_id), m.PrivateReplyJob.claim_version == version,
                m.PrivateReplyJob.status == 'processing', m.PrivateReplyJob.lease_until > self.clock(),
            ).values(response_snapshot=command, status='prepared', updated_at=self.clock()))
            if result.rowcount != 1:
                raise StaleClaim('私信领取已失效')

    async def finish(self, job_id, version, status, reason=''):
        async with self.db.session() as session, session.begin():
            await session.execute(update(m.PrivateReplyJob).where(
                m.PrivateReplyJob.job_id == int(job_id), m.PrivateReplyJob.claim_version == version,
                m.PrivateReplyJob.status.not_in(('sent', 'unknown')),
            ).values(status=status, reason_code=reason, lease_until=None, updated_at=self.clock()))

    async def state(self, ai_id, person_id):
        async with self.db.session() as session:
            return await session.get(m.PrivateContactState, (ai_id, int(person_id)))

    async def reserve(self, ai_id, person_id, run_id, revision, cooldown_sec, quiet_sec):
        now = self.clock()
        async with self.db.session() as session, session.begin():
            state = await self.contact(session, ai_id, person_id)
            if (state.status != 'active' or state.pending_run_id or state.unanswered_count >= 3
                    or state.revision != revision):
                return False
            if state.last_success_at and now - state.last_success_at < timedelta(seconds=cooldown_sec):
                return False
            if state.last_inbound_at and now - state.last_inbound_at < timedelta(seconds=quiet_sec):
                return False
            state.pending_run_id = run_id
            state.pending_revision = revision
            state.updated_at = now
            return True

    async def initialize(self, ai_id, person_id, *, new_person=False):
        async with self.db.session() as session, session.begin():
            await session.execute(insert(m.PrivateContactState).values(
                ai_id=ai_id, person_id=int(person_id), status='active' if new_person else 'suspended',
                reason_code='' if new_person else 'migration',
            ).on_conflict_do_nothing())

    async def mark_pending_unknown(self, ai_id, person_id, run_id, reason):
        async with self.db.session() as session, session.begin():
            state = await self.contact(session, ai_id, person_id)
            if state.pending_run_id != run_id:
                return False
            state.status = 'unknown'
            state.reason_code = reason
            state.updated_at = self.clock()
            return True

    async def cleanup(self):
        async with self.db.session() as session, session.begin():
            await session.execute(update(m.PrivateReplyJob).where(
                m.PrivateReplyJob.status.in_(('sent', 'failed')), m.PrivateReplyJob.retain_until < self.clock(),
            ).values(message_snapshot={}, response_snapshot=None))
