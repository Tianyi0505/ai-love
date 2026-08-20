from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver.context import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from extensions.mcp.mcp_resources import MCPResources
from extensions.mcp.weather.weather_tool_settings import (
    QWeatherClientSettings,
    WeatherToolSettings,
)
from shared.configuration.yaml_settings_loader import YamlSettingsLoader

CONFIG_PATH = Path(__file__).with_name("weather_tool.yaml")
WEATHER_SETTINGS = YamlSettingsLoader.load_section(CONFIG_PATH, "weather", WeatherToolSettings)
CLIENT_SETTINGS = YamlSettingsLoader.load_section(CONFIG_PATH, "client", QWeatherClientSettings)


# 注册天气
def register_weather(mcp) -> None:
    # 查询天气信息
    @mcp.tool(
        name=WEATHER_SETTINGS.name,
        title=WEATHER_SETTINGS.title,
        description=WEATHER_SETTINGS.description,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def weather(
        ctx: Context[MCPResources, object],
        city: Annotated[
            str,
            Field(
                min_length=WEATHER_SETTINGS.city.min_length,
                description=WEATHER_SETTINGS.city.description,
            ),
        ],
        days: Annotated[
            int,
            Field(
                ge=WEATHER_SETTINGS.days.min,
                le=WEATHER_SETTINGS.days.max,
                description=WEATHER_SETTINGS.days.description,
            ),
        ] = WEATHER_SETTINGS.days.default,
        lang: Annotated[
            str,
            Field(
                min_length=WEATHER_SETTINGS.lang.min_length,
                max_length=WEATHER_SETTINGS.lang.max_length,
                description=WEATHER_SETTINGS.lang.description,
            ),
        ] = WEATHER_SETTINGS.lang.default,
    ) -> dict:
        return await ctx.request_context.lifespan.weather.weather(
            city=city,
            days=days,
            lang=lang,
        )
