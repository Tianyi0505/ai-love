CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ai_profiles (
    ai_id text PRIMARY KEY,
    definition_version integer NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'inactive')),
    model_profile_id text NOT NULL DEFAULT 'default',
    voice_profile_id text NOT NULL DEFAULT 'default',
    avatar_profile_id text NOT NULL DEFAULT 'default',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_accounts (
    account_id text PRIMARY KEY,
    platform text NOT NULL,
    platform_account_id text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    credential_ref text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'offline',
    is_live_platform boolean NOT NULL DEFAULT false,
    allows_multi_ai boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, platform_account_id)
);

CREATE TABLE IF NOT EXISTS ai_account_bindings (
    binding_id uuid PRIMARY KEY,
    account_id text NOT NULL,
    ai_id text NOT NULL,
    bound_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    UNIQUE NULLS NOT DISTINCT (account_id, ai_id, ended_at)
);

CREATE OR REPLACE FUNCTION enforce_account_binding_cardinality()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    multi_allowed boolean;
    active_count integer;
BEGIN
    IF NEW.ended_at IS NOT NULL THEN
        RETURN NEW;
    END IF;
    SELECT allows_multi_ai INTO multi_allowed
      FROM social_accounts WHERE account_id = NEW.account_id FOR UPDATE;
    IF NOT COALESCE(multi_allowed, false) THEN
        SELECT count(*) INTO active_count
          FROM ai_account_bindings
         WHERE account_id = NEW.account_id
           AND ended_at IS NULL
           AND binding_id <> NEW.binding_id;
        IF active_count > 0 THEN
            RAISE EXCEPTION 'non-live account % already has an active AI owner', NEW.account_id;
        END IF;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_account_binding_cardinality ON ai_account_bindings;
CREATE TRIGGER trg_account_binding_cardinality
BEFORE INSERT OR UPDATE OF account_id, ended_at ON ai_account_bindings
FOR EACH ROW EXECUTE FUNCTION enforce_account_binding_cardinality();

CREATE TABLE IF NOT EXISTS persons (
    person_id uuid PRIMARY KEY,
    display_name text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_identities (
    identity_id uuid PRIMARY KEY,
    person_id uuid NOT NULL,
    platform text NOT NULL,
    account_id text NOT NULL,
    platform_user_id text NOT NULL,
    verified_by text NOT NULL,
    verified_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, account_id, platform_user_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id uuid PRIMARY KEY,
    platform text NOT NULL,
    account_id text NOT NULL,
    platform_chat_id text NOT NULL,
    chat_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, account_id, platform_chat_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL,
    ai_id text,
    platform_identity_id uuid,
    role text NOT NULL,
    content jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    retain_until timestamptz,
    correlation_id text NOT NULL
);

CREATE TABLE IF NOT EXISTS live_sessions (
    session_id text PRIMARY KEY,
    account_id text NOT NULL,
    director_policy_id text NOT NULL,
    status text NOT NULL,
    started_at timestamptz,
    ended_at timestamptz
);

CREATE TABLE IF NOT EXISTS live_session_actors (
    session_id text NOT NULL,
    ai_id text NOT NULL,
    stage_slot text NOT NULL,
    is_lead boolean NOT NULL DEFAULT false,
    talk_weight real NOT NULL DEFAULT 1,
    PRIMARY KEY (session_id, ai_id)
);

CREATE TABLE IF NOT EXISTS person_relationships (
    ai_id text NOT NULL,
    person_id uuid NOT NULL,
    familiarity real NOT NULL DEFAULT 0,
    affinity real NOT NULL DEFAULT 0,
    trust real NOT NULL DEFAULT 0,
    importance real NOT NULL DEFAULT 0,
    ceiling_policy text NOT NULL DEFAULT 'default',
    last_interaction_at timestamptz,
    PRIMARY KEY (ai_id, person_id)
);

CREATE TABLE IF NOT EXISTS group_relationships (
    ai_id text NOT NULL,
    account_id text NOT NULL,
    platform_group_id text NOT NULL,
    familiarity real NOT NULL DEFAULT 0,
    belonging real NOT NULL DEFAULT 0,
    affinity real NOT NULL DEFAULT 0,
    activity_willingness real NOT NULL DEFAULT 0,
    ceiling_policy text NOT NULL DEFAULT 'default',
    last_interaction_at timestamptz,
    PRIMARY KEY (ai_id, account_id, platform_group_id)
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id uuid PRIMARY KEY,
    owner_ai_id text,
    person_id uuid,
    session_id text,
    scope text NOT NULL CHECK (scope IN ('private', 'session', 'shared')),
    memory_type text NOT NULL,
    content text NOT NULL,
    embedding vector(1536),
    importance real NOT NULL,
    strength real NOT NULL,
    confidence real NOT NULL,
    emotion_intensity real NOT NULL DEFAULT 0,
    protected boolean NOT NULL DEFAULT false,
    dormant boolean NOT NULL DEFAULT false,
    source jsonb NOT NULL DEFAULT '{}'::jsonb,
    shared_with text[] NOT NULL DEFAULT '{}',
    consolidated boolean NOT NULL DEFAULT false,
    reference_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_strength_at timestamptz NOT NULL DEFAULT now(),
    last_recalled_at timestamptz,
    recall_count integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_revisions (
    revision_id uuid PRIMARY KEY,
    memory_id uuid NOT NULL,
    supersedes_memory_id uuid,
    changed_by text NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id uuid PRIMARY KEY,
    actor_type text NOT NULL,
    actor_id text NOT NULL,
    action text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    reason text NOT NULL DEFAULT '',
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extension_catalog (
    tool_id text PRIMARY KEY,
    provider_id text NOT NULL,
    definition jsonb NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_extension_bindings (
    ai_id text NOT NULL,
    tool_id text NOT NULL,
    permission text NOT NULL CHECK (permission IN ('allow', 'conditional', 'confirm', 'deny')),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (ai_id, tool_id)
);

CREATE TABLE IF NOT EXISTS model_profiles (
    model_profile_id text PRIMARY KEY,
    config jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
