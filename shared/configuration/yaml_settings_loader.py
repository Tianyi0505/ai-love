from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

SettingsT = TypeVar("SettingsT", bound=BaseModel)


class YamlSettingsLoader:
    @staticmethod
    def load_section(path: Path, section: str, settings_type: type[SettingsT]) -> SettingsT:
        with path.open(encoding="utf-8") as config_file:
            document = yaml.safe_load(config_file)
        return settings_type.model_validate(document[section])
