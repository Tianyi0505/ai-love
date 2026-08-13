
from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from services.mcp_weather.client import QWeatherClient

mcp = MCPServer(
    "qweather",
    version="1.0.0",
    instructions="查询和风天气的实时天气和每日预报。数据来自 QWeather。",
)


@mcp.tool(
    name="weather",
    title="查询天气",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def weather(
    city: Annotated[str, Field(min_length=1, description="城市、地区、LocationID 或经纬度")],
    days: Annotated[int, Field(ge=1, le=10, description="预报天数，1 到 10 天")] = 3,
    lang: Annotated[str, Field(min_length=2, max_length=10, description="返回语言，默认中文 zh")] = "zh",
) -> dict:
    """查询指定地点的实时天气及未来每日预报"""
    return await QWeatherClient().weather(city=city, days=days, lang=lang)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8011,
        json_response=True,
        stateless_http=True,
    )
