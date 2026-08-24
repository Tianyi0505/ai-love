from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from extensions.mcp.music.music_tool_settings import MusicToolSettings
from shared.configuration.yaml_settings_loader import YamlSettingsLoader

logger = logging.getLogger("ailove.mcp.music")

MUSIC_SETTINGS = YamlSettingsLoader.load_section(
    Path(__file__).with_name("music_tool.yaml"),
    "music",
    MusicToolSettings,
)


# 注册音乐
def register_music(mcp) -> None:
    # 执行音乐控制命令
    @mcp.tool(
        name=MUSIC_SETTINGS.name,
        title=MUSIC_SETTINGS.title,
        description=MUSIC_SETTINGS.description,
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False),
    )
    async def music_control(
        action: Annotated[
            Literal["play", "pause", "resume", "stop", "next", "volume"],
            Field(description=MUSIC_SETTINGS.action_description),
        ],
        query: Annotated[
            str,
            Field(description=MUSIC_SETTINGS.query_description),
        ] = "",
        volume: Annotated[
            int | None,
            Field(
                ge=MUSIC_SETTINGS.volume_min,
                le=MUSIC_SETTINGS.volume_max,
                description=MUSIC_SETTINGS.volume_description,
            ),
        ] = None,
    ) -> dict:
        command = {"action": action, "query": query, "volume": volume}
        logger.info("[music] 指令: %s", command)
        return {
            "accepted": True,
            "command": command,
            "note": MUSIC_SETTINGS.adapter_note,
        }
