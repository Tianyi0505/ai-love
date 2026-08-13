
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from services.mcp_weather.client import QWeatherClient
from shared.infrastructure.runtime_config import required_config


with Path(__file__).with_name("tool.yaml").open(encoding="utf-8") as config_file:
    TOOL_CONFIG = yaml.safe_load(config_file)
if not isinstance(TOOL_CONFIG, dict):
    raise RuntimeError("services.mcp_weather.tool 配置必须是对象")
SERVER_CONFIG = dict(required_config(TOOL_CONFIG, "server", "services.mcp_weather.tool.server"))
WEATHER_CONFIG = dict(required_config(TOOL_CONFIG, "weather", "services.mcp_weather.tool.weather"))
CLIENT_CONFIG = dict(required_config(TOOL_CONFIG, "client", "services.mcp_weather.tool.client"))
CITY_CONFIG = dict(required_config(WEATHER_CONFIG, "city", "services.mcp_weather.tool.weather.city"))
DAYS_CONFIG = dict(required_config(WEATHER_CONFIG, "days", "services.mcp_weather.tool.weather.days"))
LANG_CONFIG = dict(required_config(WEATHER_CONFIG, "lang", "services.mcp_weather.tool.weather.lang"))

mcp = MCPServer(
    str(required_config(SERVER_CONFIG, "name", "services.mcp_weather.tool.server.name")),
    version=str(required_config(SERVER_CONFIG, "version", "services.mcp_weather.tool.server.version")),
    instructions=str(required_config(SERVER_CONFIG, "instructions", "services.mcp_weather.tool.server.instructions")),
)


@mcp.tool(
    name=str(required_config(WEATHER_CONFIG, "name", "services.mcp_weather.tool.weather.name")),
    title=str(required_config(WEATHER_CONFIG, "title", "services.mcp_weather.tool.weather.title")),
    description=str(required_config(WEATHER_CONFIG, "description", "services.mcp_weather.tool.weather.description")),
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
    return await QWeatherClient(float(CLIENT_CONFIG["request_timeout_sec"])).weather(
        city=city, days=days, lang=lang
    )


if __name__ == "__main__":
    mcp.run(
        transport=str(SERVER_CONFIG["transport"]),
        host=str(SERVER_CONFIG["host"]),
        port=int(SERVER_CONFIG["port"]),
        json_response=bool(SERVER_CONFIG["json_response"]),
        stateless_http=bool(SERVER_CONFIG["stateless_http"]),
    )
