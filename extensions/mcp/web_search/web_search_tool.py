from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from extensions.mcp.mcp_resources import MCPResources
from extensions.mcp.web_search.web_search_tool_settings import WebSearchToolSettings
from shared.yaml_settings_loader import YamlSettingsLoader

SEARCH_SETTINGS = YamlSettingsLoader.load_section(
    Path(__file__).with_name("web_search_tool.yaml"),
    "web_search",
    WebSearchToolSettings,
)


# 注册网页检索
def register_web_search(mcp) -> None:
    # 搜索网页信息
    @mcp.tool(
        name=SEARCH_SETTINGS.name,
        title=SEARCH_SETTINGS.title,
        description=SEARCH_SETTINGS.description,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    async def web_search(
        ctx: Context[MCPResources, object],
        query: Annotated[
            str,
            Field(
                min_length=SEARCH_SETTINGS.query_min_length,
                max_length=SEARCH_SETTINGS.query_max_length,
                description=SEARCH_SETTINGS.query_description,
            ),
        ],
    ) -> str:
        result_limit = SEARCH_SETTINGS.result_limit
        results = await ctx.request_context.lifespan_context.web_search.search(query)
        if not results:
            return Template(SEARCH_SETTINGS.messages.no_result).substitute(query=query)
        result_template = Template(SEARCH_SETTINGS.messages.result)
        return "\n".join(
            result_template.substitute(
                index=index + 1,
                title=result.title,
                url=result.url,
                snippet=result.snippet,
            )
            for index, result in enumerate(results[:result_limit])
        )
