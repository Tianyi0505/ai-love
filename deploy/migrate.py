
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg


async def run() -> None:
    url = os.environ.get("AILOVE_DATABASE_URL", "")
    if not url:
        raise RuntimeError("未配置 AILOVE_DATABASE_URL")
    conn = await asyncpg.connect(url)
    try:
        for path in sorted((Path(__file__).parent / "sql").glob("*.sql")):
            await conn.execute(path.read_text(encoding="utf-8"))
            print(f"applied {path.name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
