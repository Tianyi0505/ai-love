
from __future__ import annotations

import json
import re
import time

import httpx


def _get_gtk(skey: str) -> int:
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7fffffff


class QZoneAPI:

    def __init__(self, cookie: str, uin: str = "") -> None:
        self._cookie = cookie
        self._uin = uin
        m = re.search(r"skey=([^;]+)", cookie)
        self._gtk = _get_gtk(m.group(1)) if m else 0
        self._headers = {
            "Cookie": cookie,
            "Referer": f"https://user.qzone.qq.com/{uin}",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _parse(self, text: str) -> dict:
        text = text.strip()
        m = re.search(r"\((\{.*\})\)", text, re.S)
        if m:
            return json.loads(m.group(1))
        try:
            return json.loads(text)
        except Exception:
            return {}

    async def _post(self, url: str, data: dict) -> dict:
        data["g_tk"] = self._gtk
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=self._headers, data=data)
        return self._parse(resp.text)

    async def _get(self, url: str, params: dict) -> dict:
        params["g_tk"] = self._gtk
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers, params=params)
        return self._parse(resp.text)

    async def list_feeds(self, num: int = 10) -> list[dict]:
        return await self.list_feeds_by_uin(self._uin, num)

    async def list_feeds_by_uin(self, target_uin: str, num: int = 10) -> list[dict]:
        url = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
        data = await self._get(url, {"uin": target_uin, "ftype": 0, "sort": 0, "pos": 0, "num": num, "replynum": 3})
        return data.get("msglist") or []

    async def like(self, tid: str, owner_uin: str, abstime: int = 0) -> bool:
        url = f"https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app?g_tk={self._gtk}"
        mood_url = f"http://user.qzone.qq.com/{owner_uin}/mood/{tid}"
        data = {
            "opuin": self._uin,
            "qzreferrer": f"https://user.qzone.qq.com/{self._uin}",
            "unikey": mood_url,
            "curkey": mood_url,
            "appid": "311",
            "from": "1",
            "typeid": "0",
            "abstime": str(abstime or int(time.time())),
            "fid": tid,
            "active": "0",
            "format": "json",
            "fupdate": "1",
        }
        result = await self._post(url, data)
        return result.get("code") == 0

    async def list_comments(self, tid: str, owner_uin: str, num: int = 20) -> list[dict]:
        url = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_get_comment_v6"
        data = await self._get(url, {"uin": owner_uin, "tid": tid, "num": num, "start": 0})
        return data.get("commentlist") or []

    async def feed_detail(self, tid: str, owner_uin: str) -> dict | None:
        feeds = await self.list_feeds_by_uin(owner_uin, num=20)
        for f in feeds:
            if f.get("tid") == tid:
                return f
        return None

    async def comment(self, tid: str, content: str, owner_uin: str) -> bool:
        url = f"https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds?g_tk={self._gtk}"
        topic_id = f"{owner_uin}_{tid}__1" if "_" not in tid else tid
        data = {
            "uin": self._uin,
            "hostUin": owner_uin,
            "feedsType": "100",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "topicId": topic_id,
            "plat": "qzone",
            "source": "ic",
            "platformid": "50",
            "format": "fs",
            "ref": "feeds",
            "content": content,
            "qzreferrer": f"https://user.qzone.qq.com/{self._uin}",
        }
        result = await self._post(url, data)
        return result.get("code") == 0
