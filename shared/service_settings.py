from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrivateReplySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scan_interval_sec: float = Field(default=5, gt=0)
    batch_size: int = Field(default=100, gt=0)
    concurrency: int = Field(default=10, gt=0)
    processing_budget_sec: float = Field(default=45, gt=0)
    lease_sec: float = Field(default=120, gt=0)
    heartbeat_sec: float = Field(default=15, gt=0)
    send_retries: int = Field(default=2, ge=0, le=2)

    @model_validator(mode="after")
    def validate_lease(self):
        if self.lease_sec <= max(self.heartbeat_sec, self.processing_budget_sec):
            raise ValueError("领取租约必须大于心跳和处理预算")
        return self


class ServiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_addr: str


class ServiceIdentitySettings(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    instance_addr: str


class GatewayAccountSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    adapter: str
    owner_ai_id: str
    config: dict[str, Any]


class GatewaySettings(ServiceSettings):
    accounts: tuple[GatewayAccountSettings, ...]
    private_reply: PrivateReplySettings = Field(default_factory=PrivateReplySettings)


class AIAgentSettings(ServiceSettings):
    catalog_poll_interval_sec: float
    account_ids_by_ai: dict[str, tuple[str, ...]]
    private_reply: PrivateReplySettings = Field(default_factory=PrivateReplySettings)


class DirectorSettings(ServiceSettings):
    session_id: str


class ExtensionHostSettings(ServiceSettings):
    mcp_discovery_timeout_sec: float = Field(default=3, gt=0)
    binding_poll_interval_sec: float
    grounding_timeout_sec: float
    mcp_url: str
    messages: dict[str, str]


class GPTSoVITSHTTPSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bind: str
    port: int
    log_level: str


class GPTSoVITSRequestLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id_min_chars: int
    ai_id_max_chars: int
    text_min_chars: int
    text_max_chars: int


class GPTSoVITSEngineSettings(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    provider: str
    request_timeout_sec: float


class GPTSoVITSVoiceSettings(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class GPTSoVITSOutputSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audio_dir: str
    file_extension: str
    pcm_bytes_per_sec: float


class GPTSoVITSSettings(ServiceSettings):
    http: GPTSoVITSHTTPSettings
    request_limits: GPTSoVITSRequestLimits
    engine: GPTSoVITSEngineSettings
    voices: dict[str, GPTSoVITSVoiceSettings]
    output: GPTSoVITSOutputSettings


class LiveEdgeSettings(ServiceSettings):
    obs_ws_url: str
    stream_key: str


class EmptyServiceSettings(ServiceSettings):
    pass


class DirectorActorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_id: str


class DirectorSessionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actors: tuple[DirectorActorSettings, ...]
    proactive_interval_sec: float
