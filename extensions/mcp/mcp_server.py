from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from mcp.server import MCPServer

from extensions.mcp.mcp_resources import MCPResources
from extensions.mcp.mcp_server_settings import MCPServerSettings
from extensions.mcp.music.music_tool import register_music
from extensions.mcp.structured_output.output_tools import register_structured_output
from extensions.mcp.weather.qweather_client import QWeatherClient
from extensions.mcp.weather.weather_tool import CLIENT_SETTINGS, register_weather
from extensions.mcp.web_search.web_search_client import WebSearchClient
from extensions.mcp.web_search.web_search_tool import SEARCH_SETTINGS, register_web_search
from shared.connection_settings import QWeatherConnectionSettings
from shared.yaml_settings_loader import YamlSettingsLoader

SERVER_SETTINGS = YamlSettingsLoader.load_section(
    Path(__file__).with_name("mcp_server.yaml"),
    "server",
    MCPServerSettings,
)


@asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[MCPResources]:
    weather_connection = QWeatherConnectionSettings()
    async with (
        httpx.AsyncClient(
            timeout=CLIENT_SETTINGS.request_timeout_sec,
            follow_redirects=False,
            headers={
                "X-QW-Api-Key": weather_connection.api_key,
                "Accept-Encoding": CLIENT_SETTINGS.accept_encoding,
            },
        ) as weather_http,
        httpx.AsyncClient(
            timeout=SEARCH_SETTINGS.request_timeout_sec,
            follow_redirects=True,
            headers={"User-Agent": SEARCH_SETTINGS.user_agent},
        ) as search_http,
    ):
        yield MCPResources(
            weather=QWeatherClient(
                weather_http,
                host=weather_connection.api_host,
                location_result_limit=CLIENT_SETTINGS.location_result_limit,
                coordinate_precision=CLIENT_SETTINGS.coordinate_precision,
                percent_multiplier=CLIENT_SETTINGS.percent_multiplier,
            ),
            web_search=WebSearchClient(
                search_http,
                endpoint=SEARCH_SETTINGS.endpoint,
                result_limit=SEARCH_SETTINGS.result_limit,
            ),
        )


mcp = MCPServer(
    SERVER_SETTINGS.name,
    version=SERVER_SETTINGS.version,
    instructions=SERVER_SETTINGS.instructions,
    lifespan=lifespan,
)

register_weather(mcp)
register_music(mcp)
register_web_search(mcp)
register_structured_output(mcp)


if __name__ == "__main__":
    mcp.run(
        transport=SERVER_SETTINGS.transport,
        host=SERVER_SETTINGS.host,
        port=SERVER_SETTINGS.port,
        json_response=SERVER_SETTINGS.json_response,
        stateless_http=SERVER_SETTINGS.stateless_http,
    )
