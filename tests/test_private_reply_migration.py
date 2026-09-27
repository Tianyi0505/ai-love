import pytest
from sqlalchemy import text

from shared.service_settings import PrivateReplySettings


@pytest.mark.asyncio
async def test_private_schema_and_config(private_database):
    async with private_database.engine.begin() as connection:
        assert (await connection.execute(text('SELECT count(*) FROM private_reply_jobs'))).scalar_one() == 0
    assert PrivateReplySettings().concurrency == 10
    with pytest.raises(ValueError):
        PrivateReplySettings(lease_sec=10)
