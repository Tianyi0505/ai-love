from __future__ import annotations

from dataclasses import dataclass

from extensions.mcp.weather.qweather_client import QWeatherClient
from extensions.mcp.web_search.web_search_client import WebSearchClient


@dataclass(frozen=True)
class MCPResources:
    weather: QWeatherClient
    web_search: WebSearchClient
