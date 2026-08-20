from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WebSearchMessages(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    no_result: str
    result: str


class WebSearchToolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    title: str
    description: str
    query_description: str
    query_min_length: int
    query_max_length: int
    request_timeout_sec: float
    endpoint: str
    user_agent: str
    result_limit: int
    messages: WebSearchMessages
