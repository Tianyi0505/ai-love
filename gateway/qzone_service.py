from __future__ import annotations

import asyncio
import logging
import random
from string import Template
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from gateway.qzone_api import QZoneAPI
from gateway.qzone_commented_feed_repository import QZoneCommentedFeedRepository
from shared.global_settings import QQSettings, TimeoutSettings

logger = logging.getLogger("ailove.qzone")


class QZoneModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class QZoneComment(QZoneModel):
    replyUin: str | int | None = None
    replyUin2: str | int | None = None
    content: str
    name: str | None = None
    nickname: str | None = None

    @property
    def author_name(self) -> str:
        if self.name is not None:
            return self.name
        if self.nickname is not None:
            return self.nickname
        raise ValueError("QQ 空间评论缺少作者名称")


class QZoneFeed(QZoneModel):
    tid: str
    uin: str | int
    timestamp: int = Field(validation_alias=AliasChoices("timestamp", "created_time"))
    content: str | None = None
    text: str | None = None
    name: str | None = None
    nickname: str | None = None
    pic: Any | None = None
    pics: Any | None = None
    commentlist: list[QZoneComment] = Field(default_factory=list)
    reply_context: str | None = None

    @field_validator("commentlist", mode="before")
    @classmethod
    def normalize_commentlist(cls, value):
        return [] if value is None else value

    @property
    def author_name(self) -> str:
        if self.name is not None:
            return self.name
        if self.nickname is not None:
            return self.nickname
        raise ValueError("QQ 空间动态缺少作者名称")

    @property
    def body(self) -> str:
        if self.content is not None:
            return self.content
        if self.text is not None:
            return self.text
        raise ValueError("QQ 空间动态缺少文本内容")


# 处理QQ空间互动任务
class QZoneService:
    # 初始化当前实例
    def __init__(
        self,
        napcat_http_url: str,
        qq_settings: QQSettings,
        qq_uin: str,
        relationship_provider,
        comment_generator,
        proactive_allowed,
        timeouts: TimeoutSettings,
        http_client,
        commented_repo: QZoneCommentedFeedRepository,
    ) -> None:
        self._napcat_url = napcat_http_url
        self._settings = qq_settings
        self._relationship_provider = relationship_provider
        self._comment_generator = comment_generator
        self._proactive_allowed = proactive_allowed
        self._commented = commented_repo
        self._api = None
        self._uin = qq_uin
        self._timeouts = timeouts
        self._http_client = http_client

    # 获取QQ空间接口客户端
    async def _ensure_api(self) -> None:
        if self._api is not None:
            return
        resp = await self._http_client.post(
            f"{self._napcat_url}/get_cookies",
            json={"domain": "user.qzone.qq.com"},
            timeout=self._timeouts.qzone_http_sec,
        )
        resp.raise_for_status()
        cookies = resp.json()["data"]["cookies"]
        if not cookies:
            raise RuntimeError("拿不到 QQ 空间 cookie")
        self._api = QZoneAPI(
            cookies,
            timeout_sec=self._timeouts.qzone_api_sec,
            uin=self._uin,
            http_client=self._http_client,
        )

    # 加载联系人关系
    async def _relationship(self, user_id: str) -> dict:
        return await self._relationship_provider(user_id)

    # 计算主动动作概率
    def _action_probabilities(self, relationship: dict) -> tuple[float, float]:
        lower = self._settings.qzone_relationship_score_min
        upper = self._settings.qzone_relationship_score_max
        top_familiarity = max(lower, min(upper, float(relationship["top_familiarity"])))
        familiarity = max(lower, min(upper, float(relationship["familiarity"])))
        if top_familiarity > lower and familiarity > lower:
            exponent = self._settings.qzone_relationship_curve_exponent
            normalized = (familiarity / top_familiarity) ** exponent
        else:
            normalized = familiarity
        like_probability = min(self._settings.qzone_probability_max, normalized)
        comment_probability = min(self._settings.qzone_probability_max, normalized)
        return like_probability, comment_probability

    # 回复已收到回应的动态
    async def _reply_if_replied(self, feed: QZoneFeed) -> None:
        comments = [
            QZoneComment.model_validate(item)
            for item in await self._api.list_comments(
                feed.tid,
                str(feed.uin),
                num=self._settings.qzone_comments_fetch_limit,
            )
        ]
        for comment in comments:
            reply_to = comment.replyUin if comment.replyUin is not None else comment.replyUin2
            if str(reply_to) == self._uin:
                reply_feed = feed.model_copy(update={"reply_context": comment.content})
                text = await self._comment_text(reply_feed)
                await self._api.comment(feed.tid, text, owner_uin=str(feed.uin))
                logger.info("[qzone] 回复了评论互动: %s", feed.tid)
                return

    # 提取评论文本
    async def _comment_text(self, feed: QZoneFeed) -> str:
        picture_urls = self._picture_urls(feed)
        comments = feed.commentlist
        comment_summary = ""
        if comments:
            limit = self._settings.qzone_comments_context_limit
            names = [comment.author_name for comment in comments[:limit]]
            comment_summary = Template(self._settings.qzone_existing_comments_template).substitute(
                names=", ".join(names)
            )
        reply_context = feed.reply_context
        reply_summary = (
            Template(self._settings.qzone_reply_template).substitute(content=reply_context)
            if reply_context is not None
            else ""
        )
        feed_text = (
            Template(self._settings.qzone_feed_template)
            .substitute(
                content=feed.body,
                pictures="",
                comments=comment_summary,
                reply=reply_summary,
            )
            .strip()
        )
        return await self._comment_generator(feed_text, feed.author_name, picture_urls)

    # 提取图片地址
    @staticmethod
    def _picture_urls(feed: QZoneFeed) -> list[str]:
        pictures = feed.pic if feed.pic is not None else feed.pics
        if pictures is None:
            return []
        if isinstance(pictures, dict):
            pictures = [pictures]
        urls: list[str] = []
        if not isinstance(pictures, list):
            raise ValueError("QQ 空间动态图片字段格式错误")
        for picture in pictures:
            if isinstance(picture, str):
                url = picture
            elif isinstance(picture, dict):
                url = next(
                    (
                        str(picture[key])
                        for key in ("url3", "url2", "url1", "origin_url", "smallurl", "url")
                        if key in picture and picture[key]
                    ),
                    None,
                )
            else:
                raise ValueError("QQ 空间动态图片项格式错误")
            if url is not None and url not in urls:
                urls.append(url)
        return urls

    # 处理单条空间动态，单条失败不阻断本轮其他好友动态
    async def _process_feed(self, feed: QZoneFeed, stats: dict) -> None:
        author_id = str(feed.uin)
        if await self._commented.has(feed.tid):
            await self._reply_if_replied(feed)
            return
        relationship = await self._relationship(author_id)
        like_prob, comment_prob = self._action_probabilities(relationship)
        if random.random() < like_prob:
            ok = await self._api.like(feed.tid, owner_uin=author_id, abstime=feed.timestamp)
            if ok:
                stats["liked"] += 1
            await asyncio.sleep(self._settings.qzone_action_delay_sec)
        if random.random() < comment_prob:
            text = await self._comment_text(feed)
            ok = await self._api.comment(feed.tid, text, owner_uin=author_id)
            if ok:
                stats["commented"] += 1
                await self._commented.add(feed.tid)
            await asyncio.sleep(self._settings.qzone_action_delay_sec)
        await self._commented.add(feed.tid)

    # 执行一次任务
    async def run_once(self) -> dict:
        stats = {"scanned": 0, "liked": 0, "commented": 0, "failed": 0, "skipped": False}
        if not self._proactive_allowed():
            stats.update({"skipped": True, "reason": "outside_work_hours"})
            return stats
        await self._ensure_api()
        resp = await self._http_client.post(
            f"{self._napcat_url}/get_friend_list",
            json={},
            timeout=self._timeouts.qzone_http_sec,
        )
        resp.raise_for_status()
        friends = resp.json()["data"]
        feeds = []
        for friend in friends:
            friend_uin = str(friend["user_id"])
            friend_feeds = await self._api.list_feeds_by_uin(
                friend_uin,
                num=self._settings.qzone_feeds_per_friend,
            )
            feeds.extend(QZoneFeed.model_validate(item) for item in friend_feeds)
            await asyncio.sleep(self._settings.qzone_friend_scan_delay_sec)
        stats["scanned"] = len(feeds)
        for feed in feeds:
            try:
                await self._process_feed(feed, stats)
            except Exception as exc:
                stats["failed"] += 1
                logger.warning("[qzone] 单条动态处理失败: %s: %s", feed.tid, exc)
        logger.info("[qzone] 完成一轮: %s", stats)
        return stats
