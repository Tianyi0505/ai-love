CREATE TABLE IF NOT EXISTS group_members (
    platform text NOT NULL,
    account_id text NOT NULL,
    chat_id text NOT NULL,
    platform_user_id text NOT NULL,
    person_id uuid NOT NULL,
    nickname text NOT NULL DEFAULT '',
    group_card text NOT NULL DEFAULT '',
    role text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    is_active boolean NOT NULL DEFAULT true,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, account_id, chat_id, platform_user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_scope_role
    ON group_members(platform, account_id, chat_id, role) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_group_members_person
    ON group_members(person_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS person_mentions (
    mention_id uuid PRIMARY KEY,
    mention_text text NOT NULL,
    normalized_mention text NOT NULL,
    person_id uuid NOT NULL,
    scope_type text NOT NULL CHECK (scope_type IN ('global', 'group', 'private', 'conversation')),
    scope_id text NOT NULL DEFAULT '',
    conversation_id uuid,
    source_message_id text NOT NULL DEFAULT '',
    evidence_type text NOT NULL,
    confidence real NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (normalized_mention, person_id, scope_type, scope_id, evidence_type, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_person_mentions_lookup
    ON person_mentions(normalized_mention, scope_type, scope_id, observed_at DESC);
