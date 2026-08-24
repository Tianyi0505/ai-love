from gateway.qzone_service import QZoneFeed


def test_qzone_feed_accepts_live_created_time_and_null_comments() -> None:
    feed = QZoneFeed.model_validate(
        {
            "tid": "feed-1",
            "uin": 123456,
            "created_time": 1787531378,
            "content": "测试动态",
            "name": "联系人",
            "commentlist": None,
        }
    )

    assert feed.timestamp == 1787531378
    assert feed.commentlist == []
