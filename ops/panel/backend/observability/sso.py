from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_nacos_secret(secret: str) -> bytes:
    encoded = "".join(secret.split())
    remainder = len(encoded) % 4
    if remainder == 1:
        encoded = encoded[:-1]
    elif remainder:
        encoded += "=" * (4 - remainder)
    return base64.b64decode(encoded, altchars=b"-_", validate=False)


def create_nacos_access_token(
    secret: str,
    username: str,
    *,
    expires_in_seconds: int = 3600,
    now: int | None = None,
) -> str:
    key = _decode_nacos_secret(secret)
    if len(key) < 32:
        raise ValueError("Nacos 鉴权密钥长度不足")

    if len(key) < 48:
        algorithm, digest = "HS256", hashlib.sha256
    elif len(key) < 64:
        algorithm, digest = "HS384", hashlib.sha384
    else:
        algorithm, digest = "HS512", hashlib.sha512

    header = _base64url(json.dumps({"alg": algorithm}, separators=(",", ":")).encode())
    payload = _base64url(
        json.dumps(
            {
                "sub": username,
                "exp": (int(time.time()) if now is None else now) + expires_in_seconds,
            },
            separators=(",", ":"),
        ).encode()
    )
    content = f"{header}.{payload}"
    signature = _base64url(hmac.new(key, content.encode(), digest).digest())
    return f"{content}.{signature}"


async def create_dashboard_session(
    base_url: str,
    service_account_token_path: Path,
) -> str:
    bearer = service_account_token_path.read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        verify=False,
        timeout=10.0,
    ) as client:
        csrf_response = await client.get("/api/v1/csrftoken/login")
        csrf_response.raise_for_status()
        csrf_token = csrf_response.json()["token"]
        login_response = await client.post(
            "/api/v1/login",
            json={"token": bearer},
            headers={"X-CSRF-TOKEN": csrf_token},
        )
        login_response.raise_for_status()
        session_token = login_response.json()["token"]
    if not session_token:
        raise ValueError("Dashboard 未返回会话令牌")
    return session_token
