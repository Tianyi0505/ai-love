from __future__ import annotations

import json
import uuid

from shared.contracts.turn import AgentExecutionContext
from shared.infrastructure.database import Database


# 管理执行链路与步骤持久化
class AgentRunRepository:
    # 初始化当前实例
    def __init__(self, db: Database) -> None:
        self._db = db

    # 开始一轮执行
    async def start_run(self, run: AgentExecutionContext) -> None:
        await self._db.execute(
            "INSERT INTO agent_runs(run_id,ai_id,account_id,conversation_id,platform,chat_type,chat_id,"
            "sender_person_id,source,message_id,reply_to_message_id,status,started_at) "
            "VALUES($1::uuid,$2,$3,$4::uuid,$5,$6,$7,$8::uuid,$9,$10,$11,'running',now())",
            run.run_id,
            run.ai_id,
            run.account_id or "",
            self._uuid_or_none(run.conversation_id),
            run.platform or "",
            run.chat_type or "",
            run.chat_id or "",
            self._uuid_or_none(run.sender_person_id),
            run.source,
            run.message_id or "",
            run.reply_to_message_id or "",
        )

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
        await self._db.execute(
            "INSERT INTO agent_run_steps(step_id,run_id,step_index,step_type,status,content,duration_ms,error,occurred_at) "
            "VALUES($1::uuid,$2::uuid,$3,$4,$5,$6::jsonb,$7,$8,now())",
            str(uuid.uuid4()),
            run_id,
            int(step_index),
            step_type,
            status,
            json.dumps(content or {}, ensure_ascii=False),
            int(duration_ms),
            str(error or ""),
        )

    # 完成一轮执行
    async def finish_run(
        self,
        run_id: str,
        outcome: str,
        *,
        tool_rounds: int = 0,
        response_text: str = "",
    ) -> None:
        await self._db.execute(
            "UPDATE agent_runs SET status='finished',outcome=$2,tool_rounds=$3,response_text=$4,finished_at=now() "
            "WHERE run_id=$1::uuid",
            run_id,
            outcome,
            int(tool_rounds),
            str(response_text or ""),
        )

    # 回放一轮执行链路
    async def replay(self, run_id: str) -> dict:
        run_row = await self._db.fetchrow(
            "SELECT run_id::text,ai_id,account_id,conversation_id::text,platform,chat_type,chat_id,"
            "sender_person_id::text,source,message_id,reply_to_message_id,status,outcome,tool_rounds,"
            "response_text,started_at,finished_at FROM agent_runs WHERE run_id=$1::uuid",
            run_id,
        )
        if run_row is None:
            return {"run": None, "steps": []}
        steps = await self._db.fetch(
            "SELECT step_index,step_type,status,content,duration_ms,error,occurred_at "
            "FROM agent_run_steps WHERE run_id=$1::uuid ORDER BY step_index,occurred_at",
            run_id,
        )
        return {
            "run": dict(run_row),
            "steps": [dict(row) for row in steps],
        }

    # 列出会话近期执行
    async def list_runs(self, ai_id: str, conversation_id: str, limit: int) -> list[dict]:
        rows = await self._db.fetch(
            "SELECT run_id::text,source,status,outcome,tool_rounds,started_at,finished_at "
            "FROM agent_runs WHERE ai_id=$1 AND conversation_id=$2::uuid "
            "ORDER BY started_at DESC LIMIT $3",
            ai_id,
            conversation_id,
            int(limit),
        )
        return [dict(row) for row in rows]

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
        conditions: list[str] = []
        args: list = []
        if ai_id:
            args.append(ai_id)
            conditions.append(f"ai_id=${len(args)}")
        if conversation_id:
            try:
                uuid.UUID(conversation_id)
            except (ValueError, TypeError, AttributeError):
                return []
            args.append(conversation_id)
            conditions.append(f"conversation_id=${len(args)}::uuid")
        if source:
            args.append(source)
            conditions.append(f"source=${len(args)}")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.append(int(max(1, min(200, limit))))
        args.append(int(max(0, offset)))
        rows = await self._db.fetch(
            "SELECT run_id::text,ai_id,account_id,conversation_id::text,platform,chat_type,chat_id,"
            "sender_person_id::text,source,message_id,reply_to_message_id,status,outcome,tool_rounds,"
            f"response_text,started_at,finished_at FROM agent_runs {where} "
            f"ORDER BY started_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}",
            *args,
        )
        return [dict(row) for row in rows]

    # 转换可选 UUID
    @staticmethod
    def _uuid_or_none(value: str) -> str | None:
        if not value:
            return None
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            return None
