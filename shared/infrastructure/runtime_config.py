
from __future__ import annotations

import os


def required_value(value: str | None, config_name: str) -> str:
    resolved = (value or "").strip()
    if not resolved:
        raise RuntimeError(f"未配置 {config_name}")
    return resolved


def required_setting(value: str | None, env_name: str) -> str:
    return required_value(value or os.environ.get(env_name, ""), env_name)
