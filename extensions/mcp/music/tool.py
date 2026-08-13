from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

import yaml
from mcp.types import ToolAnnotations
from pydantic import Field

from shared.infrastructure.runtime_config import required_config

logger = logging.getLogger("ailove.mcp.music")

with Path(__file__).with_name("tool.yaml").open(encoding="utf-8") as config_file:
    CONFIG = yaml.safe_load(config_file)
if not isinstance(CONFIG, dict):
    raise RuntimeError("extensions.mcp.music.tool 配置必须是对象")
MUSIC_CONFIG = dict(
    required_config(CONFIG, "music", "extensions.mcp.music.tool.music")
)


# 注册音乐
def register_music(mcp) -> None:
    # 执行音乐控制命令
    @mcp.tool(
        name=str(required_config(MUSIC_CONFIG, "name", "extensions.mcp.music.tool.music.name")),
        title=str(required_config(MUSIC_CONFIG, "title", "extensions.mcp.music.tool.music.title")),
        description=str(
            required_config(
                MUSIC_CONFIG,
                "description",
                "extensions.mcp.music.tool.music.description",
            )
        ),
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False),
    )
    async def music_control(
        action: Annotated[
            Literal["play", "pause", "resume", "stop", "next", "volume"],
            Field(description=str(MUSIC_CONFIG["action_description"])),
        ],
        query: Annotated[
            str,
            Field(description=str(MUSIC_CONFIG["query_description"])),
        ] = "",
        volume: Annotated[
            int | None,
            Field(ge=0, le=100, description=str(MUSIC_CONFIG["volume_description"])),
        ] = None,
    ) -> dict:
        command = {"action": action, "query": query, "volume": volume}
        logger.info("[music] 指令: %s", command)
        return {
            "accepted": True,
            "command": command,
            "note": str(MUSIC_CONFIG["adapter_note"]),
        }
