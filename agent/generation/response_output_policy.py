from __future__ import annotations

from agent.generation.response_plan import ParticipationDecision, ResponsePlan
from shared.configuration.global_settings import ResponseOutputLimits


class ResponseOutputPolicy:
    def __init__(self, limits: ResponseOutputLimits) -> None:
        self._limits = limits

    def validate_plan(self, plan: ResponsePlan) -> ResponsePlan:
        limits = self._limits
        for speech in plan.speech:
            if not limits.speech_min_chars <= len(speech.text) <= limits.speech_max_chars:
                raise ValueError("回复文本长度不符合配置")
        for action in plan.actions:
            if not limits.action_query_min_chars <= len(action.query) <= limits.action_query_max_chars:
                raise ValueError("动作查询长度不符合配置")
        if not limits.emotion_intensity_min <= plan.emotion.intensity <= limits.emotion_intensity_max:
            raise ValueError("情绪强度不符合配置")
        return plan

    def validate_participation(self, decision: ParticipationDecision) -> ParticipationDecision:
        limits = self._limits
        if not limits.participation_reason_min_chars <= len(decision.reason) <= limits.participation_reason_max_chars:
            raise ValueError("参与理由长度不符合配置")
        return decision
