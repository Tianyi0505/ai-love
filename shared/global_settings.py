from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QQSettings(SettingsModel):
    whitelist: tuple[int, ...]
    group_member_refresh_sec: float
    voice_reply: bool
    space_interval_sec: float
    qzone_comments_context_limit: int
    qzone_comments_fetch_limit: int
    qzone_feeds_per_friend: int
    qzone_friend_scan_delay_sec: float
    qzone_action_delay_sec: float
    qzone_comment_max_sentences: int
    qzone_data_dir: str
    qzone_relationship_curve_exponent: float
    qzone_relationship_score_min: float
    qzone_relationship_score_max: float
    qzone_probability_max: float
    qzone_picture_template: str
    qzone_picture_unavailable_template: str
    qzone_existing_comments_template: str
    qzone_reply_template: str
    qzone_feed_template: str


class StickerRetentionWeights(SettingsModel):
    match_quality: float
    usage_strength: float
    freshness: float


class StickerSearchWeights(SettingsModel):
    lexical: float
    match_quality: float
    usage_strength: float
    freshness: float


class StickerSettings(SettingsModel):
    capacity: int
    half_life_sec: float
    boost_delta: float
    usage_strength_max: float
    threshold: float
    collect_min_quality: float
    list_limit: int
    initial_usage_strength: float
    initial_boost_count: int
    boost_count_increment: int
    search_candidate_limit: int
    search_min_score: float
    retention_weights: StickerRetentionWeights
    search_weights: StickerSearchWeights


class SocialSettings(SettingsModel):
    contact_names: dict[str, str]
    send_timeout_sec: float
    window_size: int
    prompt_history_messages: int
    live_prompt_history_messages: int
    channel_history_since: float
    channel_history_limit: int
    drain_poll_interval_sec: float
    session_state_ttl_sec: int
    message_retention_days: int
    log_preview_chars: int


class LiveSettings(SettingsModel):
    default_interaction_type: str
    default_importance: int


class GroundingSettings(SettingsModel):
    candidate_limit: int
    mention_evidence_half_life_sec: float
    history_default_limit: int
    history_max_limit: int
    history_lookback_sec: float
    person_context_fact_limit: int
    recent_participants_limit: int
    recent_participants_lookback_sec: float
    relevant_people_limit: int
    group_memory_top_k_per_person: int
    group_memory_result_limit: int
    explicit_mention_confidence: float
    ignored_mention_names: frozenset[str]
    confidence_min: float
    confidence_max: float
    role_unique_confidence: float
    role_ambiguous_confidence: float
    platform_identity_confidence: float
    group_card_confidence: float
    display_name_confidence: float
    recency_base: float
    evidence_confidence_max: float
    evidence_boost_max: float
    evidence_boost_per_occurrence: float
    ambiguous_name_confidence: float
    resolved_confidence_threshold: float
    at_candidate_limit: int
    quote_candidate_limit: int
    role_candidate_limit: int
    primary_candidate_limit: int
    member_name_min_chars: int
    role_names: dict[str, tuple[str, ...]]


class ResponseOutputLimits(SettingsModel):
    speech_min_chars: int
    speech_max_chars: int
    action_query_min_chars: int
    action_query_max_chars: int
    participation_reason_min_chars: int
    participation_reason_max_chars: int
    emotion_intensity_min: float
    emotion_intensity_max: float


class ChatModelSettings(SettingsModel):
    provider: str
    model: str
    base_url: str
    api_key_env: str


class LLMSettings(SettingsModel):
    models: dict[str, ChatModelSettings]
    timeout_ms: int
    health_fail_threshold: int
    health_recover_after_sec: float
    max_requests: int
    participation_max_requests: int
    memory_max_requests: int
    memory_max_tokens: int
    memory_request_timeout_sec: float
    max_tokens: int
    retry_count: int
    tool_retry_count: int
    provider_request_timeout_sec: float
    output_limits: ResponseOutputLimits


class TTSSettings(SettingsModel):
    provider: str
    base_url: str


class VisionOutputLimits(SettingsModel):
    description_min_chars: int
    description_max_chars: int
    sticker_description_max_chars: int
    emotion_max_chars: int
    tags_max_count: int
    match_quality_min: float
    match_quality_max: float


class ImageSettings(SettingsModel):
    model: str
    base_url: str
    api_key_env: str
    fetch_timeout_sec: float
    request_timeout_sec: float
    max_tokens: int
    retry_count: int
    media_type: str
    fetch_headers: dict[str, str]
    output_limits: VisionOutputLimits
    prompt: str


class TokenEstimationSettings(SettingsModel):
    characters_per_token: int
    minimum_tokens: int


class MemoryOutputLimits(SettingsModel):
    episode_summary_min_chars: int
    episode_summary_max_chars: int
    memories_max_count: int
    memory_content_min_chars: int
    memory_content_max_chars: int
    importance_min: float
    importance_max: float
    confidence_min: float
    confidence_max: float
    markdown_min_chars: int
    markdown_max_chars: int


class MemoryGenerationSettings(SettingsModel):
    output_limits: MemoryOutputLimits


class MemoryDocumentSchema(SettingsModel):
    title: str
    sections: tuple[str, ...]
    empty_document: str
    identity_section: str | None = None

    @model_validator(mode="after")
    def validate_identity_section(self):
        if self.identity_section is not None and self.identity_section not in self.sections:
            raise ValueError("固定身份章节必须在文档章节中声明")
        return self


class MemoryDocumentSchemas(SettingsModel):
    person: MemoryDocumentSchema
    self: MemoryDocumentSchema


class MemoryEpisodeSettings(SettingsModel):
    history_episode_limit: int


class MemoryExtractionSettings(SettingsModel):
    quiet_window_sec: float
    scheduler_poll_sec: float
    retry_delay_sec: float


class MemoryConsolidationThresholds(SettingsModel):
    min_episode_count: int
    min_atom_count: int
    token_threshold: int
    max_wait_sec: float


class MemoryConsolidationSettings(SettingsModel):
    scheduler_poll_sec: float
    retry_delay_sec: float
    person: MemoryConsolidationThresholds
    self: MemoryConsolidationThresholds


class MemoryRetrievalWeights(SettingsModel):
    relevance: float
    strength: float
    importance: float
    confidence: float
    emotion_intensity: float


class LFUDomainSettings(SettingsModel):
    decay_interval_sec: float
    log_factor: float
    log_offset: int
    max_counter: int
    score_counter_ceiling: int
    initial_counter: int


class LFUSettings(SettingsModel):
    relationship: LFUDomainSettings
    memory: LFUDomainSettings
    evidence: LFUDomainSettings


class MemorySettings(SettingsModel):
    data_dir: str
    cleanup_interval_sec: float
    file_max_age_sec: float
    worker_concurrency: int
    worker_lease_sec: float
    state_cas_retry_count: int
    token_estimation: TokenEstimationSettings
    generation: MemoryGenerationSettings
    document_schemas: MemoryDocumentSchemas
    episode: MemoryEpisodeSettings
    extraction: MemoryExtractionSettings
    consolidation: MemoryConsolidationSettings
    search_top_k: int
    database_candidate_limit: int
    record_capacity_per_owner: int
    atom_capacity_per_owner: int
    empty_query_relevance: float
    half_life_sec: float
    dormant_threshold: float
    delete_threshold: float
    recall_boost: float
    strength_max: float
    elapsed_floor_sec: float
    deletable_reference_count: int
    recall_count_increment: int
    initial_document_version: int
    document_version_increment: int
    retrieval_weights: MemoryRetrievalWeights


class TimeoutSettings(SettingsModel):
    relationship_update_sec: float
    relationship_summary_sec: float
    relationship_list_sec: float
    relationship_group_sec: float
    memory_write_sec: float
    memory_search_sec: float
    memory_context_sec: float
    tool_list_sec: float
    tool_execute_sec: float
    tts_request_sec: float
    social_history_sec: float
    sticker_add_sec: float
    sticker_boost_sec: float
    comment_generation_sec: float
    friend_list_sec: float
    qzone_http_sec: float
    qzone_api_sec: float
    qq_message_sec: float
    qq_forward_sec: float
    web_search_sec: float


class RelationshipStorageSettings(SettingsModel):
    initial_score: float
    default_ceiling_policy: str
    whitelist_ceiling_policy: str
    latest_identity_limit: int


class ObservabilitySettings(SettingsModel):
    include_model_content: bool
    include_binary_content: bool
    include_model_request_parameters: bool


class GlobalSettings(SettingsModel):
    qq: QQSettings
    sticker: StickerSettings
    social: SocialSettings
    live: LiveSettings
    grounding: GroundingSettings
    llm: LLMSettings
    tts: TTSSettings
    image: ImageSettings
    lfu: LFUSettings
    memory: MemorySettings
    relationship_storage: RelationshipStorageSettings
    timeouts: TimeoutSettings
    observability: ObservabilitySettings
