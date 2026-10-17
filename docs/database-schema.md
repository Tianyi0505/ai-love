# Database Schema

PostgreSQL stores the current durable state. SQLAlchemy models and Alembic migrations define the schema.

## Identity and delivery

| Table | Purpose |
| --- | --- |
| ai_profiles | Stores AI profile records. |
| social_accounts | Stores platform accounts. |
| ai_account_bindings | Stores trusted AI-to-account ownership. |
| model_profiles | Stores model-profile records. |
| private_reply_jobs | Stores durable private-reply work. |
| private_contact_states | Stores private-contact scheduling state. |
| social_deliveries | Stores social delivery state and recovery data. |

## People and conversations

| Table | Purpose |
| --- | --- |
| persons | Stores person records. |
| platform_identities | Maps platform identities to persons. |
| group_members | Stores group membership snapshots. |
| person_mentions | Stores grounded person references. |
| person_mention_frequencies | Stores mention frequency state. |
| conversations | Stores conversation records. |
| messages | Stores source and generated messages. |
| person_relationships | Stores AI-to-person relationship state. |
| group_relationships | Stores AI-to-group relationship state. |

## Memory and social assets

| Table | Purpose |
| --- | --- |
| memories | Stores legacy memory records. |
| memory_revisions | Stores memory revisions. |
| conversation_episodes | Stores quiet-window episodes. |
| memory_atoms | Stores source-backed memory facts. |
| memory_documents | Stores consolidated person and self documents. |
| conversation_summaries | Stores conversation summaries. |
| stickers | Stores approved sticker assets and scores. |
| qzone_commented_feeds | Stores QZone interaction state. |

## Live, plugin, and operations state

| Table | Purpose |
| --- | --- |
| live_sessions | Stores live sessions. |
| live_session_actors | Stores active session actors. |
| extension_catalog | Stores plugin catalog entries. |
| ai_extension_bindings | Stores AI tool bindings. |
| audit_log | Stores audited operations. |
| panel_settings | Stores admin-console settings. |

The source model file shared/database_models.py defines columns, indexes, and constraints.
