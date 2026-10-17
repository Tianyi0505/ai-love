# Relationship Signals

Conversation activity drives relationship updates. The relationship policy applies the configured conversation, trust, and group-conversation values.

## Current results

- Person relationships store familiarity, affinity, trust, importance, and related state.
- Group relationships store familiarity, belonging, affinity, activity willingness, and related state.
- Gateway events use the declared interaction types.
- Relationship settings use the RelationshipConfigModel contract.
- Live importance and memory importance retain separate meanings.

The relationship repository, QZone context provider, and relationship handler use the shared relationship state.
