
from __future__ import annotations

import asyncio
import json
import logging
import random
from string import Template

import httpx

from gateway.commented_repo import CommentedRepo
from gateway.qzone_api import QZoneAPI

logger = logging.getLogger("ailove.qzone")


class QZoneService:

    def __init__(
        self,
        napcat_http_url: str,
        gcfg,
        qq_uin: str,
        relationship_provider,
        comment_generator,
        proactive_allowed,
        timeouts: dict,
    ) -> None:
        self._napcat_url = napcat_http_url
        self._gcfg = gcfg
        self._relationship_provider = relationship_provider
        self._comment_generator = comment_generator
        self._proactive_allowed = proactive_allowed
        self._commented = CommentedRepo(str(gcfg.get("qq", "qzone_data_dir")))
        self._api = None
        self._uin = qq_uin
        self._timeouts = timeouts

    async def _ensure_api(self) -> None:
        if self._api is not None:
            return
        async with httpx.AsyncClient(timeout=float(self._timeouts["qzone_http_sec"])) as client:
            resp = await client.post(f"{self._napcat_url}/get_cookies", json={"domain": "user.qzone.qq.com"})
            cookies = resp.json().get("data", {}).get("cookies", "")
        if not cookies:
            raise RuntimeError("拿不到 QQ 空间 cookie")
        self._api = QZoneAPI(
            cookies,
            timeout_sec=float(self._timeouts["qzone_api_sec"]),
            uin=self._uin,
        )

    async def _relationship(self, user_id: str) -> dict:
        return await self._relationship_provider(user_id)

    def _action_probabilities(self, relationship: dict) -> tuple[float, float]:
        top_familiarity = max(
            0.0,
            min(1.0, float(relationship.get("top_familiarity", 0.0) or 0.0)),
        )
        familiarity = max(0.0, min(1.0, float(relationship.get("familiarity", 0.0))))
        if top_familiarity > 0 and familiarity > 0:
            exponent = float(self._gcfg.get("qq", "qzone_relationship_curve_exponent"))
            normalized = (familiarity / top_familiarity) ** exponent
        else:
            normalized = familiarity
        like_probability = min(1.0, normalized)
        comment_probability = min(1.0, normalized)
        return like_probability, comment_probability

    async def _reply_if_replied(self, tid: str, owner_uin: str, feed: dict, author_name: str) -> None:
        try:
            comments = await self._api.list_comments(
                tid,
                owner_uin,
                num=int(self._gcfg.get("qq", "qzone_comments_fetch_limit")),
            )
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
        comments = feed.get("commentlist") or []
        comment_summary = ""
        if comments:
            limit = int(self._gcfg.get("qq", "qzone_comments_context_limit"))
            person_name = str(self._gcfg.get("fallbacks", "person_name"))
            names = [c.get("name") or c.get("nickname") or person_name for c in comments[:limit]]
            comment_summary = Template(str(self._gcfg.get("qq", "qzone_existing_comments_template"))).substitute(
                names=", ".join(names)
            )
        reply_context = feed.get("reply_context", "")
        reply_summary = (
            Template(str(self._gcfg.get("qq", "qzone_reply_template"))).substitute(
                content=reply_context
            )
            if reply_context
            else ""
        )
        feed_text = Template(str(self._gcfg.get("qq", "qzone_feed_template"))).substitute(
            content=content,
            pictures="",
            comments=comment_summary,
            reply=reply_summary,
        ).strip() or str(self._gcfg.get("fallbacks", "qzone_empty_feed"))
        try:
            resp = await self._comment_generator(feed_text, author_name, picture_urls)
            if resp:
                return resp
        except Exception as e:
            logger.warning("[qzone] 智能评论生成失败: %s", e)
        templates = self._gcfg.get("qq", "qzone_fallback_comments")
        return Template(str(random.choice(templates))).substitute(author_name=author_name)

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
            async with httpx.AsyncClient(timeout=float(self._timeouts["qzone_http_sec"])) as client:
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
                friend_feeds = await self._api.list_feeds_by_uin(
                    friend_uin,
                    num=int(self._gcfg.get("qq", "qzone_feeds_per_friend")),
                )
                feeds.extend(friend_feeds)
            except Exception as e:
                logger.warning("[qzone] 查好友 %s 动态失败: %s", friend_uin, e)
            await asyncio.sleep(float(self._gcfg.get("qq", "qzone_friend_scan_delay_sec")))
        stats["scanned"] = len(feeds)
        for feed in feeds:
            try:
                tid = feed.get("tid", "")
                if not tid:
                    continue
                author_id = str(feed.get("uin", ""))
                author_name = (
                    feed.get("name")
                    or feed.get("nickname")
                    or self._gcfg.get("fallbacks", "person_name")
                )
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
                    await asyncio.sleep(float(self._gcfg.get("qq", "qzone_action_delay_sec")))
                if random.random() < comment_prob:
                    text = await self._comment_text(feed, author_name)
                    ok = await self._api.comment(tid, text, owner_uin=owner_uin)
                    if ok:
                        stats["commented"] += 1
                        self._commented.add(tid)
                    await asyncio.sleep(float(self._gcfg.get("qq", "qzone_action_delay_sec")))
                self._commented.add(tid)
            except Exception as e:
                stats["errors"] += 1
                logger.warning("[qzone] 处理动态失败: %s", e)
        logger.info("[qzone] 完成一轮: %s", stats)
        return stats

    async def loop(self) -> None:
        interval = int(self._gcfg.get("qq", "space_interval_sec"))
        while True:
            try:
                stats = await self.run_once()
                if not stats.get("skipped"):
                    logger.info("[qzone] 轮次完成: %s", stats)
            except Exception as e:
                logger.warning("[qzone] 轮次失败: %s", e)
            await asyncio.sleep(interval)
