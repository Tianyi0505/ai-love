
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.contracts.turn import AgentExecutionContext
from shared.infrastructure.database import Database
from shared.infrastructure import models as m
from shared.infrastructure.snowflake import is_snowflake_id, new_snowflake_id


# 管理执行链路与步骤持久化
class AgentRunRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 开始一轮执行
    async def start_run(self, run: AgentExecutionContext) -> None:
        async with self._db.session() as session:
            session.add(
                m.AgentRun(
                    run_id=int(run.run_id),
                    ai_id=run.ai_id,
                    account_id=run.account_id or "",
                    conversation_id=self._id_or_none(run.conversation_id),
                    platform=run.platform or "",
                    chat_type=run.chat_type or "",
                    chat_id=run.chat_id or "",
                    sender_person_id=self._id_or_none(run.sender_person_id),
                    source=run.source,
                    message_id=run.message_id or "",
                    reply_to_message_id=run.reply_to_message_id or "",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    # 记录执行步骤
    async def record_step(
        self,
        run_id: str,
        step_index: int,
        step_type: str,
        *,
        status: str = "ok",
        content: dict | None = None,
        duration_ms: int = 0,
        error: str = "",
    ) -> None:
        async with self._db.session() as session:
            session.add(
                m.AgentRunStep(
                    step_id=int(new_snowflake_id()),
                    run_id=int(run_id),
                    step_index=int(step_index),
                    step_type=step_type,
                    status=status,
                    content=content or {},
                    duration_ms=int(duration_ms),
                    error=str(error or ""),
                    occurred_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    # 完成一轮执行
    async def finish_run(
        self,
        run_id: str,
        outcome: str,
        *,
        tool_rounds: int = 0,
        response_text: str = "",
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(m.AgentRun)
                .where(m.AgentRun.run_id == int(run_id))
                .values(
                    status="finished",
                    outcome=outcome,
                    tool_rounds=int(tool_rounds),
                    response_text=str(response_text or ""),
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    # 回放一轮执行链路
    async def replay(self, run_id: str) -> dict:
        async with self._db.session() as session:
            run_row = (
                await session.execute(
                    select(m.AgentRun).where(m.AgentRun.run_id == int(run_id))
                )
            ).scalar_one_or_none()
            if run_row is None:
                return {"run": None, "steps": []}
            steps = await session.execute(
                select(
                    m.AgentRunStep.step_index,
                    m.AgentRunStep.step_type,
                    m.AgentRunStep.status,
                    m.AgentRunStep.content,
                    m.AgentRunStep.duration_ms,
                    m.AgentRunStep.error,
                    m.AgentRunStep.occurred_at,
                )
                .where(m.AgentRunStep.run_id == int(run_id))
                .order_by(m.AgentRunStep.step_index, m.AgentRunStep.occurred_at)
            )
            return {
                "run": {
                    "run_id": str(run_row.run_id),
                    "ai_id": run_row.ai_id,
                    "account_id": run_row.account_id,
                    "conversation_id": str(run_row.conversation_id)
                    if run_row.conversation_id is not None
                    else None,
                    "platform": run_row.platform,
                    "chat_type": run_row.chat_type,
                    "chat_id": run_row.chat_id,
                    "sender_person_id": str(run_row.sender_person_id)
                    if run_row.sender_person_id is not None
                    else None,
                    "source": run_row.source,
                    "message_id": run_row.message_id,
                    "reply_to_message_id": run_row.reply_to_message_id,
                    "status": run_row.status,
                    "outcome": run_row.outcome,
                    "tool_rounds": run_row.tool_rounds,
                    "response_text": run_row.response_text,
                    "started_at": run_row.started_at,
                    "finished_at": run_row.finished_at,
                },
                "steps": [
                    {
                        "step_index": row.step_index,
                        "step_type": row.step_type,
                        "status": row.status,
                        "content": row.content,
                        "duration_ms": row.duration_ms,
                        "error": row.error,
                        "occurred_at": row.occurred_at,
                    }
                    for row in steps
                ],
            }

    # 列出会话近期执行
    async def list_runs(self, ai_id: str, conversation_id: str, limit: int) -> list[dict]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.AgentRun.run_id,
                    m.AgentRun.source,
                    m.AgentRun.status,
                    m.AgentRun.outcome,
                    m.AgentRun.tool_rounds,
                    m.AgentRun.started_at,
                    m.AgentRun.finished_at,
                )
                .where(
                    m.AgentRun.ai_id == ai_id,
                    m.AgentRun.conversation_id == int(conversation_id),
                )
                .order_by(m.AgentRun.started_at.desc())
                .limit(int(limit))
            )
            return [
                {
                    "run_id": str(row.run_id),
                    "source": row.source,
                    "status": row.status,
                    "outcome": row.outcome,
                    "tool_rounds": row.tool_rounds,
                    "started_at": row.started_at,
                    "finished_at": row.finished_at,
                }
                for row in rows
            ]

    # 按条件查询执行记录
    async def search_runs(
        self,
        *,
        ai_id: str = "",
        conversation_id: str = "",
        source: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = []
        if ai_id:
            conditions.append(m.AgentRun.ai_id == ai_id)
        if conversation_id:
            if not is_snowflake_id(conversation_id):
                return []
            conditions.append(m.AgentRun.conversation_id == int(conversation_id))
        if source:
            conditions.append(m.AgentRun.source == source)
        async with self._db.session() as session:
            rows = await session.execute(
                select(
                    m.AgentRun.run_id,
                    m.AgentRun.ai_id,
                    m.AgentRun.account_id,
                    m.AgentRun.conversation_id,
                    m.AgentRun.platform,
                    m.AgentRun.chat_type,
                    m.AgentRun.chat_id,
                    m.AgentRun.sender_person_id,
                    m.AgentRun.source,
                    m.AgentRun.message_id,
                    m.AgentRun.reply_to_message_id,
                    m.AgentRun.status,
                    m.AgentRun.outcome,
                    m.AgentRun.tool_rounds,
                    m.AgentRun.response_text,
                    m.AgentRun.started_at,
                    m.AgentRun.finished_at,
                )
                .where(*conditions)
                .order_by(m.AgentRun.started_at.desc())
                .limit(int(max(1, min(200, limit))))
                .offset(int(max(0, offset)))
            )
            return [
                {
                    "run_id": str(row.run_id),
                    "ai_id": row.ai_id,
                    "account_id": row.account_id,
                    "conversation_id": str(row.conversation_id)
                    if row.conversation_id is not None
                    else None,
                    "platform": row.platform,
                    "chat_type": row.chat_type,
                    "chat_id": row.chat_id,
                    "sender_person_id": str(row.sender_person_id)
                    if row.sender_person_id is not None
                    else None,
                    "source": row.source,
                    "message_id": row.message_id,
                    "reply_to_message_id": row.reply_to_message_id,
                    "status": row.status,
                    "outcome": row.outcome,
                    "tool_rounds": row.tool_rounds,
                    "response_text": row.response_text,
                    "started_at": row.started_at,
                    "finished_at": row.finished_at,
                }
                for row in rows
            ]

    # 转换可选ID
    @staticmethod
    def _id_or_none(value: str) -> int | None:
        if not value:
            return None
        return int(value) if is_snowflake_id(value) else None
