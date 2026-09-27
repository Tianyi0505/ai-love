"""私信处理边界：持久领取、非空回应、发送结果恢复。"""
import asyncio
import logging
from dataclasses import replace

from agent.social.social_message_handler import _process
from shared import private_reply_observability as private_metrics
from shared.contracts.rpc.social import (
    SocialSendRequest,
    SocialSendResponse,
    SocialSendStatusRequest,
    SocialSendStatusResponse,
)
from shared.contracts.social import SocialMessage
from shared.contracts.turn import AgentExecutionContext, ResponseCommand

logger = logging.getLogger('ailove.agent.private')


class PrivateReplyService:
    def __init__(self, runtime, jobs, settings):
        self.runtime = runtime
        self.jobs = jobs
        self.settings = settings
        self.semaphore = asyncio.Semaphore(settings.concurrency)

    def fallback(self, message, reason):
        private_metrics.fallback(reason)
        execution = AgentExecutionContext.from_social_message(message, self.runtime.ai_id)
        key = 'private-reply-unavailable' if reason != 'input' else 'private-reply-unrecognized'
        text = self.runtime.prompt_assembler.render(key)
        return ResponseCommand(run_id=execution.run_id, ai_id=execution.ai_id,
            account_id=execution.account_id, conversation_id=execution.conversation_id,
            platform=execution.platform, chat=message.chat.model_dump(mode='json'),
            reply_to_message_id=execution.reply_to_message_id, text=text, sticker=None, voice=None)

    async def _heartbeat(self, job):
        while True:
            await asyncio.sleep(self.settings.heartbeat_sec)
            if not await self.jobs.heartbeat(job.job_id, job.claim_version, self.settings.lease_sec):
                return

    async def handle(self, job_id):
        async with self.semaphore:
            job = await self.jobs.claim(job_id, self.runtime.ai_id, self.settings.lease_sec)
            if job is None:
                return
            pulse = asyncio.create_task(self._heartbeat(job))
            try:
                await self._run(job)
            finally:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)

    async def _run(self, job):
        runtime = self.runtime
        message = SocialMessage.model_validate(job.message_snapshot)
        message.meta['run_id'] = job.run_id
        if job.response_snapshot:
            request = SocialSendRequest.model_validate(job.response_snapshot).model_copy(
                update={'claim_version': job.claim_version})
        else:
            if message.meta.get('private_input_error'):
                command = self.fallback(message, 'input')
            elif job.reason_code == 'interrupted':
                command = self.fallback(message, 'interrupted')
            else:
                try:
                    async with asyncio.timeout(self.settings.processing_budget_sec):
                        execution = AgentExecutionContext.from_social_message(message, runtime.ai_id)
                        private_metrics.model_call()
                        command = await _process(runtime, message, execution, send=False)
                    if not isinstance(command, ResponseCommand) or not (command.text or '').strip():
                        command = self.fallback(message, 'empty')
                except Exception as exc:
                    logger.warning('private_fallback run_id=%s reason=%s', job.run_id, type(exc).__name__)
                    command = self.fallback(message, 'generation')
            command = replace(command, run_id=job.run_id, delivery_kind='private_reply',
                source_job_id=str(job.job_id), claim_version=job.claim_version, person_id=str(job.person_id))
            request = command.send_request()
            await self.jobs.prepare(job.job_id, job.claim_version, request.model_dump(mode='json'))
        try:
            await runtime.bus.request_model('social.send.request', request,
                SocialSendResponse,
                timeout=runtime.settings.social.send_timeout_sec)
        except Exception as exc:
            try:
                status = await runtime.bus.request_model('social.send.status.request',
                    SocialSendStatusRequest(ai_id=job.ai_id, account_id=job.account_id, run_id=job.run_id),
                    SocialSendStatusResponse, timeout=runtime.settings.social.send_timeout_sec)
            except Exception:
                status = SocialSendStatusResponse(status='unknown')
            if status.status == 'sent':
                await self.jobs.finish(job.job_id, job.claim_version, 'sent')
                private_metrics.result('sent')
                await self._after_sent(job, message, request)
            elif status.status == 'failed' and not status.retryable:
                await self.jobs.finish(job.job_id, job.claim_version, 'failed', status.reason_code)
                private_metrics.result('failed', status.reason_code)
            else:
                await self.jobs.finish(job.job_id, job.claim_version, 'unknown', type(exc).__name__)
                private_metrics.result('unknown', type(exc).__name__)
                logger.error('private_delivery_unknown run_id=%s', job.run_id)
            return
        await self.jobs.finish(job.job_id, job.claim_version, 'sent')
        private_metrics.result('sent')
        await self._after_sent(job, message, request)

    async def _after_sent(self, job, message, request):
        runtime = self.runtime
        runtime.conversation.add_ai('private', message.chat.chat_id, request.text)
        try:
            await runtime.memory.activity(person_id=str(job.person_id), conversation_id=str(job.conversation_id),
                                          message_id=message.message_id)
        except Exception:
            logger.warning('private_memory_pending run_id=%s', job.run_id)

    async def scan(self):
        pending = await self.jobs.pending(('ready', 'processing', 'prepared'),
                                          self.settings.batch_size, self.runtime.ai_id)
        private_metrics.pending(pending)
        results = await asyncio.gather(*(self.handle(job.job_id) for job in pending), return_exceptions=True)
        for job, result in zip(pending, results, strict=True):
            if isinstance(result, BaseException):
                logger.error('private_job_error run_id=%s reason=%s', job.run_id, type(result).__name__)

    async def loop(self):
        while True:
            try:
                await self.scan()
            except Exception as exc:
                private_metrics.scan_failure('agent', type(exc).__name__)
                logger.error('private_scan_failed reason=%s', type(exc).__name__)
            await asyncio.sleep(self.settings.scan_interval_sec)
