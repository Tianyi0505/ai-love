from __future__ import annotations

import json
import re
import time

import httpx


# 获取GTK令牌
def _get_gtk(skey: str) -> int:
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


# 封装QQ空间接口调用
class QZoneAPI:
    # 初始化当前实例
    def __init__(
        self,
        cookie: str,
        timeout_sec: float,
        uin: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._cookie = cookie
        self._uin = uin
        m = re.search(r"skey=([^;]+)", cookie)
        self._gtk = _get_gtk(m.group(1)) if m else 0
        self._timeout_sec = timeout_sec
        self._client = http_client
        self._headers = {
            "Cookie": cookie,
            "Referer": f"https://user.qzone.qq.com/{uin}",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    # 解析输入数据
    def _parse(self, text: str) -> dict:
        text = text.strip()
        m = re.search(r"\((\{.*\})\)", text, re.S)
        if m:
            return json.loads(m.group(1))
        return json.loads(text)

    # 发送HTTP请求
    async def _post(self, url: str, data: dict) -> dict:
        data["g_tk"] = self._gtk
        resp = await self._client.post(
            url,
            headers=self._headers,
            data=data,
            timeout=self._timeout_sec,
        )
        resp.raise_for_status()
        return self._parse(resp.text)

    # 获取数据
    async def _get(self, url: str, params: dict) -> dict:
        params["g_tk"] = self._gtk
        resp = await self._client.get(
            url,
            headers=self._headers,
            params=params,
            timeout=self._timeout_sec,
        )
        resp.raise_for_status()
        return self._parse(resp.text)

    # 列出动态列表
    async def list_feeds(self, num: int) -> list[dict]:
        return await self.list_feeds_by_uin(self._uin, num)

    # 按QQ号列出动态
    async def list_feeds_by_uin(self, target_uin: str, num: int) -> list[dict]:
        url = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
        data = await self._get(url, {"uin": target_uin, "ftype": 0, "sort": 0, "pos": 0, "num": num, "replynum": 3})
        return data.get("msglist") or []

    # 点赞动态
    async def like(self, tid: str, owner_uin: str, abstime: int) -> bool:
        url = (
            f"https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app?g_tk={self._gtk}"
        )
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

    # 列出评论列表
    async def list_comments(self, tid: str, owner_uin: str, num: int) -> list[dict]:
        url = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_get_comment_v6"
        data = await self._get(url, {"uin": owner_uin, "tid": tid, "num": num, "start": 0})
        return data.get("commentlist") or []

    # 获取动态详情
    async def feed_detail(self, tid: str, owner_uin: str, num: int) -> dict | None:
        feeds = await self.list_feeds_by_uin(owner_uin, num=num)
        for f in feeds:
            if f.get("tid") == tid:
                return f
        return None

    # 发表评论
    async def comment(self, tid: str, content: str, owner_uin: str) -> bool:
        url = (
            f"https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds?g_tk={self._gtk}"
        )
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
