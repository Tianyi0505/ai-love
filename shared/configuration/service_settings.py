from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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


class AIAgentSettings(ServiceSettings):
    catalog_poll_interval_sec: float
    account_ids_by_ai: dict[str, tuple[str, ...]]


class DirectorSettings(ServiceSettings):
    session_id: str


class ExtensionHostSettings(ServiceSettings):
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


class StreamSettings(ServiceSettings):
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
