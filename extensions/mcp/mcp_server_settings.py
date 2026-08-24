from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MCPServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    instructions: str
    transport: str
    host: str
    port: int
    json_response: bool
    stateless_http: bool
