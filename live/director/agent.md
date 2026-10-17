# Live Director Runtime

Start the director with python -m live.director.director_service. The director reads its session identifier from service.director and its actor list from director.<session_id>.

## Routing results

- Each live event maps to a session, a target AI, and active actors.
- Eligible actors belong to the configured session.
- Agent consumers receive events with trusted ownership.
- The deterministic policy produces the same actor selection for the same input.
- The proactive interval creates scheduled live speech opportunities.
- Shared live contracts define fields that cross gateway, director, and agent boundaries.
