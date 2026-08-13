
from __future__ import annotations

import asyncio
import json
import logging
import random

import httpx

from services.gateway.commented_repo import CommentedRepo
from services.gateway.qzone_api import QZoneAPI

logger = logging.getLogger("ailove.qzone")


class QZoneService:

    def __init__(
        self,
        napcat_http_url: str,
        gcfg,
        qq_uin: str = "",
        relationship_provider=None,
        comment_generator=None,
        proactive_allowed=None,
        image_describer=None,
    ) -> None:
        self._napcat_url = napcat_http_url
        self._gcfg = gcfg
        self._relationship_provider = relationship_provider
        self._comment_generator = comment_generator
        self._proactive_allowed = proactive_allowed or (lambda: False)
        self._image_describer = image_describer
        self._commented = CommentedRepo()
        self._api = None
        self._uin = qq_uin

    async def _ensure_api(self) -> None:
        if self._api is not None:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._napcat_url}/get_cookies", json={"domain": "user.qzone.qq.com"})
            cookies = resp.json().get("data", {}).get("cookies", "")
        if not cookies:
            raise RuntimeError("拿不到 QQ 空间 cookie")
        self._api = QZoneAPI(cookies, uin=self._uin)

    async def _relationship(self, user_id: str) -> dict:
        if self._relationship_provider is None:
            return {}
        return await self._relationship_provider(user_id)

    @staticmethod
    def _action_probabilities(relationship: dict) -> tuple[float, float]:
        top_familiarity = max(
            0.0,
            min(1.0, float(relationship.get("top_familiarity", 0.0) or 0.0)),
        )
        familiarity = max(0.0, min(1.0, float(relationship.get("familiarity", 0.0))))
        affinity = max(-1.0, min(1.0, float(relationship.get("affinity", 0.0))))
        importance = max(0.0, min(1.0, float(relationship.get("importance", 0.0))))
        positive_affinity = max(0.0, affinity)
        if top_familiarity > 0 and familiarity > 0:
            normalized = (familiarity / top_familiarity) ** 2
        else:
            normalized = familiarity
        like_probability = min(1.0, normalized)
        comment_probability = min(1.0, normalized)
        return like_probability, comment_probability

    async def _reply_if_replied(self, tid: str, owner_uin: str, feed: dict, author_name: str) -> None:
        try:
            comments = await self._api.list_comments(tid, owner_uin)
            for c in comments:
                reply_to = c.get("replyUin", "") or c.get("replyUin2", "") or ""
                if reply_to == self._uin:
                    context = dict(feed)
                    context["reply_context"] = c.get("content", "")
                    text = await self._comment_text(context, author_name)
                    await self._api.comment(tid, text, owner_uin=owner_uin)
                    logger.info("[qzone] 回复了评论互动: %s", tid)
                    return
        except Exception as e:
            logger.warning("[qzone] 回复检查失败: %s", e)

    async def _comment_text(self, feed: dict, author_name: str) -> str:
        content = feed.get("content") or feed.get("text") or ""
        picture_urls = self._picture_urls(feed)
        picture_descriptions = await self._describe_pictures(picture_urls)
        if picture_descriptions:
            pic_desc = "\n".join(
                f"[动态图片{index}：{description}]"
                for index, description in enumerate(picture_descriptions, start=1)
            )
        else:
            pic_desc = f"[附 {len(picture_urls)} 张图片，暂时无法识别]" if picture_urls else ""
        comments = feed.get("commentlist") or []
        comment_summary = ""
        if comments:
            names = [c.get("name") or c.get("nickname") or "朋友" for c in comments[:3]]
            comment_summary = f"，已有评论: {', '.join(names)}"
        reply_context = feed.get("reply_context", "")
        reply_summary = f"\n对方刚回复：{reply_context}" if reply_context else ""
        feed_text = f"{content}\n{pic_desc}{comment_summary}{reply_summary}".strip() or "（无文本）"
        try:
            if self._comment_generator is not None:
                resp = await self._comment_generator(feed_text, author_name)
                if resp:
                    return resp
        except Exception as e:
            logger.warning("[qzone] 智能评论生成失败: %s", e)
        templates = [
            f"看到{author_name}的动态啦，支持支持～",
            "哇，这个有意思！",
            "哈哈哈太真实了",
            "今天也要开心呀！",
            "来啦来啦，踩踩～",
        ]
        return random.choice(templates)

    @staticmethod
    def _picture_urls(feed: dict) -> list[str]:
        pictures = feed.get("pic") or feed.get("pics") or []
        if isinstance(pictures, dict):
            pictures = [pictures]
        urls: list[str] = []
        for picture in pictures if isinstance(pictures, list) else []:
            if isinstance(picture, str):
                url = picture
            elif isinstance(picture, dict):
                url = next(
                    (
                        str(picture.get(key))
                        for key in ("url3", "url2", "url1", "origin_url", "smallurl", "url")
                        if picture.get(key)
                    ),
                    "",
                )
            else:
                url = ""
            if url and url not in urls:
                urls.append(url)
        return urls

    async def _describe_pictures(self, urls: list[str]) -> list[str]:
        if not urls or self._image_describer is None:
            return []

        async def describe(url: str) -> str:
            try:
                result = await self._image_describer.describe(url)
                return str(result.description or "图片内容无法识别")
            except Exception as exc:
                logger.warning("[qzone] 动态图片理解失败: %s", exc)
                return "图片内容无法识别"

        return await asyncio.gather(*(describe(url) for url in urls))

    async def run_once(self) -> dict:
        stats = {"scanned": 0, "liked": 0, "commented": 0, "errors": 0, "skipped": False}
        if not self._proactive_allowed():
            stats.update({"skipped": True, "reason": "outside_work_hours"})
            return stats
        try:
            await self._ensure_api()
        except Exception as e:
            logger.warning("[qzone] cookie 获取失败: %s", e)
            stats["skipped"] = True
            return stats
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self._napcat_url}/get_friend_list", json={})
                friends = resp.json().get("data", [])
        except Exception as e:
            logger.warning("[qzone] 好友列表失败: %s", e)
            friends = []
        feeds = []
        for friend in friends:
            friend_uin = str(friend.get("user_id", ""))
            if not friend_uin:
                continue
            try:
                friend_feeds = await self._api.list_feeds_by_uin(friend_uin, num=10)
                feeds.extend(friend_feeds)
            except Exception as e:
                logger.warning("[qzone] 查好友 %s 动态失败: %s", friend_uin, e)
            await asyncio.sleep(2)
        stats["scanned"] = len(feeds)
        for feed in feeds:
            try:
                tid = feed.get("tid", "")
                if not tid:
                    continue
                author_id = str(feed.get("uin", ""))
                author_name = feed.get("name") or feed.get("nickname") or "朋友"
                owner_uin = author_id or self._uin
                if self._commented.has(tid):
                    await self._reply_if_replied(tid, owner_uin, feed, author_name)
                    continue
                abstime = int(feed.get("timestamp", 0) or 0)
                relationship = await self._relationship(author_id)
                like_prob, comment_prob = self._action_probabilities(relationship)
                if random.random() < like_prob:
                    ok = await self._api.like(tid, owner_uin=owner_uin, abstime=abstime)
                    if ok:
                        stats["liked"] += 1
                    await asyncio.sleep(3)
                if random.random() < comment_prob:
                    text = await self._comment_text(feed, author_name)
                    ok = await self._api.comment(tid, text, owner_uin=owner_uin)
                    if ok:
                        stats["commented"] += 1
                        self._commented.add(tid)
                    await asyncio.sleep(3)
                self._commented.add(tid)
            except Exception as e:
                stats["errors"] += 1
                logger.warning("[qzone] 处理动态失败: %s", e)
        logger.info("[qzone] 完成一轮: %s", stats)
        return stats

    async def loop(self) -> None:
        interval = int(self._gcfg.get("qq", "space_interval_sec", 3600))
        while True:
            try:
                stats = await self.run_once()
                if not stats.get("skipped"):
                    logger.info("[qzone] 轮次完成: %s", stats)
            except Exception as e:
                logger.warning("[qzone] 轮次失败: %s", e)
            await asyncio.sleep(interval)
