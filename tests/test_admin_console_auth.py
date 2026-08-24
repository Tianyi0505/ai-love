from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.console.backend.auth.credentials import (
    CredentialRecord,
    CredentialService,
)
from admin.console.backend.auth.login import LoginService
from admin.console.backend.auth.router import router
from admin.console.backend.auth.session import SESSION_TTL_SECONDS, RedisSessionStore


class MemoryCredentialRepository:
    def __init__(self, username: str, password_hash: str) -> None:
        self.record = CredentialRecord(username=username, password_hash=password_hash)

    async def load(self) -> CredentialRecord:
        return self.record

    async def save(self, username: str, password_hash: str) -> None:
        self.record = CredentialRecord(username=username, password_hash=password_hash)


class MemorySessionStore:
    def __init__(self) -> None:
        self.tokens: set[str] = set()
        self._sequence = 0

    async def create(self) -> str:
        self._sequence += 1
        token = f"session-{self._sequence}"
        self.tokens.add(token)
        return token

    async def exists(self, token: str) -> bool:
        return token in self.tokens

    async def delete(self, token: str) -> None:
        self.tokens.discard(token)

    async def delete_all(self) -> None:
        self.tokens.clear()


class RecordingRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)

    async def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key


def create_auth_app() -> FastAPI:
    password_hasher = PasswordHasher()
    credentials = MemoryCredentialRepository(
        "owner",
        password_hasher.hash("first-password"),
    )
    sessions = MemorySessionStore()
    app = FastAPI()
    app.state.config = SimpleNamespace(ai_id="ai_luoyu")
    app.state.session_store = sessions
    app.state.login_service = LoginService(credentials, sessions, password_hasher)
    app.state.credential_service = CredentialService(
        credentials,
        sessions,
        password_hasher,
    )
    app.include_router(router)
    return app


class AuthRouteTests(unittest.TestCase):
    def test_login_writes_http_only_cookie_and_logout_invalidates_it(self) -> None:
        with TestClient(create_auth_app()) as client:
            login = client.post(
                "/ai-love-api/login",
                json={"username": "owner", "password": "first-password"},
            )

            self.assertEqual(200, login.status_code)
            self.assertEqual("ai_luoyu", login.json()["ai_id"])
            cookie = login.headers["set-cookie"].lower()
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=lax", cookie)
            self.assertIn(f"max-age={SESSION_TTL_SECONDS}", cookie)
            self.assertEqual(200, client.get("/ai-love-api/session").status_code)

            self.assertEqual(200, client.post("/ai-love-api/logout").status_code)
            self.assertEqual(401, client.get("/ai-love-api/session").status_code)

    def test_credential_update_invalidates_every_existing_session(self) -> None:
        app = create_auth_app()
        with TestClient(app) as first, TestClient(app) as second:
            for client in (first, second):
                response = client.post(
                    "/ai-love-api/login",
                    json={"username": "owner", "password": "first-password"},
                )
                self.assertEqual(200, response.status_code)

            changed = first.post(
                "/ai-love-api/credentials",
                json={
                    "current_password": "first-password",
                    "username": "new-owner",
                    "password": "second-password",
                },
            )

            self.assertEqual(200, changed.status_code)
            self.assertEqual(401, first.get("/ai-love-api/session").status_code)
            self.assertEqual(401, second.get("/ai-love-api/session").status_code)
            relogin = first.post(
                "/ai-love-api/login",
                json={"username": "new-owner", "password": "second-password"},
            )
            self.assertEqual(200, relogin.status_code)

    def test_wrong_current_password_is_business_error_and_keeps_session(self) -> None:
        with TestClient(create_auth_app()) as client:
            client.post(
                "/ai-love-api/login",
                json={"username": "owner", "password": "first-password"},
            )

            response = client.post(
                "/ai-love-api/credentials",
                json={
                    "current_password": "wrong-password",
                    "username": "new-owner",
                    "password": "second-password",
                },
            )

            self.assertEqual(400, response.status_code)
            self.assertEqual(200, client.get("/ai-love-api/session").status_code)


class RedisSessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_hashes_token_and_uses_fixed_ttl(self) -> None:
        redis = RecordingRedis()
        store = RedisSessionStore(redis)  # type: ignore[arg-type]

        token = await store.create()

        self.assertNotIn(token, redis.values)
        expected_key = f"ai-love:session:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"
        self.assertEqual("1", redis.values[expected_key])
        self.assertEqual(SESSION_TTL_SECONDS, redis.expirations[expected_key])
        self.assertTrue(await store.exists(token))
        await store.delete(token)
        self.assertFalse(await store.exists(token))


if __name__ == "__main__":
    unittest.main()
