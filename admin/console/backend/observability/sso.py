from __future__ import annotations

from pathlib import Path

import httpx


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
