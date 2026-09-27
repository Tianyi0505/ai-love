import os

import pytest_asyncio
from private_reply_fixtures import isolated_database

os.environ.setdefault("AILOVE_SNOWFLAKE_WORKER_ID", "0")


@pytest_asyncio.fixture
async def private_database():
    url = os.environ.get("AILOVE_TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("私聊事务验收需要 AILOVE_TEST_DATABASE_URL，禁止用跳过测试冒充验证通过")
    async with isolated_database(url) as database:
        from shared import database_models as m
        models = (m.Person, m.PlatformIdentity, m.Conversation, m.Message, m.PersonRelationship,
                  m.AIAccountBinding, m.SocialAccount, m.PrivateReplyJob, m.PrivateContactState, m.SocialDelivery)
        async with database.engine.begin() as connection:
            for model in models:
                await connection.run_sync(model.__table__.create)
        yield database
