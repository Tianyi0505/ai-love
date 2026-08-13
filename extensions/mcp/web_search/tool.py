from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Annotated

import yaml
from mcp.types import ToolAnnotations
from pydantic import Field

from extensions.mcp.web_search.client import WebSearchClient
from shared.infrastructure.runtime_config import required_config


with Path(__file__).with_name("tool.yaml").open(encoding="utf-8") as config_file:
    CONFIG = yaml.safe_load(config_file)
if not isinstance(CONFIG, dict):
    raise RuntimeError("extensions.mcp.web_search.tool 配置必须是对象")
SEARCH_CONFIG = dict(
    required_config(CONFIG, "web_search", "extensions.mcp.web_search.tool.web_search")
)
MESSAGES = dict(
    required_config(
        SEARCH_CONFIG,
        "messages",
        "extensions.mcp.web_search.tool.web_search.messages",
    )
)


# 注册网页检索
def register_web_search(mcp) -> None:
    # 搜索网页信息
    @mcp.tool(
        name=str(
            required_config(
                SEARCH_CONFIG,
                "name",
                "extensions.mcp.web_search.tool.web_search.name",
            )
        ),
        title=str(
            required_config(
                SEARCH_CONFIG,
                "title",
                "extensions.mcp.web_search.tool.web_search.title",
            )
        ),
        description=str(
            required_config(
                SEARCH_CONFIG,
                "description",
                "extensions.mcp.web_search.tool.web_search.description",
            )
        ),
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def web_search(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description=str(SEARCH_CONFIG["query_description"]),
            ),
        ],
    ) -> str:
        result_limit = int(SEARCH_CONFIG["result_limit"])
        client = WebSearchClient(
            endpoint=str(SEARCH_CONFIG["endpoint"]),
            user_agent=str(SEARCH_CONFIG["user_agent"]),
            request_timeout_sec=float(SEARCH_CONFIG["request_timeout_sec"]),
            result_limit=result_limit,
        )
        results = await client.search(query)
        if not results:
            return Template(str(MESSAGES["no_result"])).substitute(query=query)
        result_template = Template(str(MESSAGES["result"]))
        return "\n".join(
            result_template.substitute(
                index=index + 1,
                title=result.title,
                url=result.url,
                snippet=result.snippet,
            )
            for index, result in enumerate(results[:result_limit])
        )
