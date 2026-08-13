CREATE TABLE IF NOT EXISTS conversation_episodes (
    episode_id uuid PRIMARY KEY,
    activity_id text NOT NULL UNIQUE,
    ai_id text NOT NULL,
    person_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    summary text NOT NULL DEFAULT '',
    source_message_ids uuid[] NOT NULL DEFAULT '{}',
    estimated_tokens integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_episodes_owner
    ON conversation_episodes(ai_id, person_id, conversation_id, ended_at DESC);

CREATE TABLE IF NOT EXISTS memory_atoms (
    atom_id uuid PRIMARY KEY,
    ai_id text NOT NULL,
    owner_type text NOT NULL CHECK (owner_type IN ('person', 'self')),
    owner_id text NOT NULL,
    person_id uuid,
    episode_id uuid NOT NULL,
    memory_type text NOT NULL,
    content text NOT NULL,
    importance real NOT NULL,
    confidence real NOT NULL,
    source_message_ids uuid[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_atoms_owner
    ON memory_atoms(ai_id, owner_type, owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_documents (
    ai_id text NOT NULL,
    owner_type text NOT NULL CHECK (owner_type IN ('person', 'self')),
    owner_id text NOT NULL,
    markdown_content text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ai_id, owner_type, owner_id)
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    ai_id text NOT NULL,
    conversation_id uuid NOT NULL,
    summary text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ai_id, conversation_id)
);
