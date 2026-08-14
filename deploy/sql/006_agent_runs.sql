CREATE TABLE IF NOT EXISTS agent_runs (
    run_id uuid PRIMARY KEY,
    ai_id text NOT NULL,
    account_id text NOT NULL DEFAULT '',
    conversation_id uuid,
    platform text NOT NULL DEFAULT '',
    chat_type text NOT NULL DEFAULT '',
    chat_id text NOT NULL DEFAULT '',
    sender_person_id uuid,
    source text NOT NULL DEFAULT 'social',
    message_id text NOT NULL DEFAULT '',
    reply_to_message_id text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'running',
    outcome text NOT NULL DEFAULT '',
    tool_rounds integer NOT NULL DEFAULT 0,
    response_text text NOT NULL DEFAULT '',
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation
    ON agent_runs(ai_id, conversation_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_message
    ON agent_runs(platform, account_id, message_id);

CREATE TABLE IF NOT EXISTS agent_run_steps (
    step_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    step_index integer NOT NULL,
    step_type text NOT NULL,
    status text NOT NULL DEFAULT 'ok',
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    duration_ms integer NOT NULL DEFAULT 0,
    error text NOT NULL DEFAULT '',
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run
    ON agent_run_steps(run_id, step_index);
