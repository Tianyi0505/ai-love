from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TextArgumentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_length: int
    description: str


class BoundedIntegerArgumentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: int
    max: int
    default: int
    description: str


class LanguageArgumentSettings(TextArgumentSettings):
    max_length: int
    default: str


class WeatherToolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    title: str
    description: str
    city: TextArgumentSettings
    days: BoundedIntegerArgumentSettings
    lang: LanguageArgumentSettings


class QWeatherClientSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_timeout_sec: float
    accept_encoding: str
    location_result_limit: int
    coordinate_precision: int
    percent_multiplier: float
