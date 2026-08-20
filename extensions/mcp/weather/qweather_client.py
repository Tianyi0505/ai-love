from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import TypeAdapter


# 调用和风天气接口
class QWeatherClient:
    # 初始化当前实例
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        host: str,
        location_result_limit: int,
        coordinate_precision: int,
        percent_multiplier: float,
    ) -> None:
        self._client = http_client
        self._host = host.removeprefix("https://").rstrip("/")
        self._location_result_limit = location_result_limit
        self._coordinate_precision = coordinate_precision
        self._percent_multiplier = percent_multiplier

    # 查询天气信息
    async def weather(self, city: str, days: int, lang: str) -> dict[str, Any]:
        location = await self._get(
            "/geo/v2/city/lookup",
            {
                "location": city,
                "number": self._location_result_limit,
                "lang": lang,
            },
        )
        matches = location.get("location") or []
        if not matches:
            raise ValueError(f"没有找到地点：{city}")
        place = matches[0]
        latitude = round(float(place["lat"]), self._coordinate_precision)
        longitude = round(float(place["lon"]), self._coordinate_precision)
        current, daily = await asyncio.gather(
            self._get(
                f"/weather/v1/current/{latitude}/{longitude}",
                {"localTime": "true", "lang": lang},
            ),
            self._get(
                f"/weather/v1/daily/{latitude}/{longitude}",
                {"days": days, "localTime": "true", "lang": lang},
            ),
        )
        return self._normalize(place, current, daily)

    # 获取数据
    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get(f"https://{self._host}{path}", params=params)
        response.raise_for_status()
        return TypeAdapter(dict[str, Any]).validate_python(response.json())

    # 规范化输入数据
    def _normalize(self, place: dict, current: dict, daily: dict) -> dict[str, Any]:
        condition = current.get("condition") or {}
        temperature = current.get("temperature") or {}
        feels_like = current.get("feelsLike") or {}
        wind = current.get("wind") or {}
        precipitation = current.get("precipitation") or {}
        current_result = {
            "condition": condition.get("text"),
            "temperature": temperature,
            "feels_like": feels_like,
            "humidity_percent": self._percent(current.get("humidity")),
            "wind_direction": (wind.get("direction") or {}).get("compass"),
            "wind_scale": wind.get("scale"),
            "wind_speed": wind.get("speed"),
            "precipitation": precipitation,
            "pressure": current.get("pressure"),
            "visibility": current.get("visibility"),
            "uv_index": current.get("uvIndex"),
        }
        forecasts = []
        for item in daily.get("days") or []:
            daytime = item.get("daytime") or {}
            nighttime = item.get("nighttime") or {}
            forecasts.append(
                {
                    "start_time": item.get("forecastStartTime"),
                    "temperature_min": item.get("temperatureMin"),
                    "temperature_max": item.get("temperatureMax"),
                    "day_condition": (daytime.get("condition") or {}).get("text"),
                    "night_condition": (nighttime.get("condition") or {}).get("text"),
                    "day_precipitation_probability_percent": self._percent(
                        (daytime.get("precipitation") or {}).get("probability")
                    ),
                    "night_precipitation_probability_percent": self._percent(
                        (nighttime.get("precipitation") or {}).get("probability")
                    ),
                    "sunrise": (item.get("astro") or {}).get("sunrise"),
                    "sunset": (item.get("astro") or {}).get("sunset"),
                }
            )
        attributions = list(
            dict.fromkeys(
                (current.get("metadata") or {}).get("attributions", [])
                + (daily.get("metadata") or {}).get("attributions", [])
            )
        )
        return {
            "location": {
                "name": place.get("name"),
                "administrative_area": place.get("adm1"),
                "country": place.get("country"),
                "latitude": place.get("lat"),
                "longitude": place.get("lon"),
                "timezone": place.get("tz"),
            },
            "current": current_result,
            "forecast": forecasts,
            "attributions": attributions,
            "source": "QWeather",
        }

    # 计算百分比值
    def _percent(self, value: Any) -> int | None:
        if value is None:
            return None
        return round(float(value) * self._percent_multiplier)
