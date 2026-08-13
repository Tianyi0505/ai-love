from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from mcp.types import ToolAnnotations
from pydantic import Field

from extensions.mcp.weather.client import QWeatherClient
from shared.infrastructure.runtime_config import required_config


with Path(__file__).with_name("tool.yaml").open(encoding="utf-8") as config_file:
    CONFIG = yaml.safe_load(config_file)
if not isinstance(CONFIG, dict):
    raise RuntimeError("extensions.mcp.weather.tool 配置必须是对象")
WEATHER_CONFIG = dict(
    required_config(CONFIG, "weather", "extensions.mcp.weather.tool.weather")
)
CLIENT_CONFIG = dict(
    required_config(CONFIG, "client", "extensions.mcp.weather.tool.client")
)
CITY_CONFIG = dict(
    required_config(WEATHER_CONFIG, "city", "extensions.mcp.weather.tool.weather.city")
)
DAYS_CONFIG = dict(
    required_config(WEATHER_CONFIG, "days", "extensions.mcp.weather.tool.weather.days")
)
LANG_CONFIG = dict(
    required_config(WEATHER_CONFIG, "lang", "extensions.mcp.weather.tool.weather.lang")
)


def register_weather(mcp) -> None:
    @mcp.tool(
        name=str(
            required_config(
                WEATHER_CONFIG,
                "name",
                "extensions.mcp.weather.tool.weather.name",
            )
        ),
        title=str(
            required_config(
                WEATHER_CONFIG,
                "title",
                "extensions.mcp.weather.tool.weather.title",
            )
        ),
        description=str(
            required_config(
                WEATHER_CONFIG,
                "description",
                "extensions.mcp.weather.tool.weather.description",
            )
        ),
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def weather(
        city: Annotated[
            str,
            Field(
                min_length=int(CITY_CONFIG["min_length"]),
                description=str(CITY_CONFIG["description"]),
            ),
        ],
        days: Annotated[
            int,
            Field(
                ge=int(DAYS_CONFIG["min"]),
                le=int(DAYS_CONFIG["max"]),
                description=str(DAYS_CONFIG["description"]),
            ),
        ] = int(DAYS_CONFIG["default"]),
        lang: Annotated[
            str,
            Field(
                min_length=int(LANG_CONFIG["min_length"]),
                max_length=int(LANG_CONFIG["max_length"]),
                description=str(LANG_CONFIG["description"]),
            ),
        ] = str(LANG_CONFIG["default"]),
    ) -> dict:
        return await QWeatherClient(
            float(CLIENT_CONFIG["request_timeout_sec"])
        ).weather(city=city, days=days, lang=lang)
