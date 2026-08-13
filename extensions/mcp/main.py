from __future__ import annotations

from pathlib import Path

import yaml
from mcp.server import MCPServer

from extensions.mcp.music.tool import register_music
from extensions.mcp.weather.tool import register_weather
from extensions.mcp.web_search.tool import register_web_search
from shared.infrastructure.runtime_config import required_config


with Path(__file__).with_name("server.yaml").open(encoding="utf-8") as config_file:
    CONFIG = yaml.safe_load(config_file)
if not isinstance(CONFIG, dict):
    raise RuntimeError("extensions.mcp.server 配置必须是对象")
SERVER_CONFIG = dict(required_config(CONFIG, "server", "extensions.mcp.server"))

mcp = MCPServer(
    str(required_config(SERVER_CONFIG, "name", "extensions.mcp.server.name")),
    version=str(required_config(SERVER_CONFIG, "version", "extensions.mcp.server.version")),
    instructions=str(
        required_config(
            SERVER_CONFIG,
            "instructions",
            "extensions.mcp.server.instructions",
        )
    ),
)

register_weather(mcp)
register_music(mcp)
register_web_search(mcp)


if __name__ == "__main__":
    mcp.run(
        transport=str(SERVER_CONFIG["transport"]),
        host=str(SERVER_CONFIG["host"]),
        port=int(SERVER_CONFIG["port"]),
        json_response=bool(SERVER_CONFIG["json_response"]),
        stateless_http=bool(SERVER_CONFIG["stateless_http"]),
    )
