
from __future__ import annotations

import asyncio
import json

import httpx
import websockets

from shared.infrastructure.runtime_config import required_setting

DEFAULT_WHITELIST = []


async def handle_request(evt: dict, whitelist: list[str], client: httpx.AsyncClient, http_url: str) -> None:
    request_type = evt.get("request_type", "")
    user_id = str(evt.get("user_id", ""))
    if request_type not in ("group", "friend") or user_id not in whitelist:
        return
    flag = evt.get("flag", "")
    sub_type = evt.get("sub_type", "add")
    action = "set_group_add_request" if request_type == "group" else "set_friend_add_request"
    payload = {
        "flag": flag,
        "approve": True,
        "sub_type": sub_type,
        "reason": "",
    }
    resp = await client.post(f"{http_url}/{action}", json=payload)
    print(f"[whitelist] 接受 {request_type} 请求: user={user_id} -> {resp.status_code}")


async def main() -> None:
    ws_url = required_setting(None, "NAPCAT_WS_URL")
    http_url = required_setting(None, "NAPCAT_HTTP_URL")
    whitelist = DEFAULT_WHITELIST  # TODO: 从 Nacos 读
    print(f"[whitelist] 白名单: {whitelist}")
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    print("[whitelist] 已连接 NapCat WS")
                    async for raw in ws:
                        evt = json.loads(raw)
                        if evt.get("post_type") == "request":
                            await handle_request(evt, whitelist, client, http_url)
            except Exception as e:
                print(f"[whitelist] 连接断开: {e}，重连中...")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
