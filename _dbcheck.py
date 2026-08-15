import asyncio
import os

import asyncpg


async def main() -> None:
    url = os.environ["AILOVE_DATABASE_URL"]
    conn = await asyncpg.connect(url, timeout=8)
    rows = await conn.fetch(
        "SELECT pid, usename, state, wait_event_type, wait_event, "
        "EXTRACT(EPOCH FROM now()-query_start)::int AS query_age_sec, "
        "EXTRACT(EPOCH FROM now()-xact_start)::int AS xact_age_sec, "
        "client_addr, LEFT(query,110) AS query "
        "FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() "
        "ORDER BY xact_age_sec DESC LIMIT 25"
    )
    print("=== pg_stat_activity ===")
    for r in rows:
        print(dict(r))
    print("=== lock waits ===")
    locks = await conn.fetch(
        "SELECT blocked.pid AS blocked_pid, blocking.pid AS blocking_pid, "
        "LEFT(blocked.query,80) AS blocked_query, blocked.state AS blocked_state, "
        "blocking.state AS blocking_state, LEFT(blocking.query,80) AS blocking_query "
        "FROM pg_stat_activity blocked "
        "JOIN pg_locks bl ON blocked.pid=bl.pid AND NOT bl.granted "
        "JOIN pg_locks bkl ON bkl.locktype=bl.locktype AND bkl.granted AND bkl.pid<>bl.pid "
        "JOIN pg_stat_activity blocking ON blocking.pid=bkl.pid "
        "WHERE blocked.datname=current_database() LIMIT 10"
    )
    for r in locks:
        print(dict(r))
    print("=== conn count by state ===")
    counts = await conn.fetch(
        "SELECT state, count(*) FROM pg_stat_activity "
        "WHERE datname=current_database() GROUP BY state"
    )
    for r in counts:
        print(dict(r))
    await conn.close()


asyncio.run(main())
