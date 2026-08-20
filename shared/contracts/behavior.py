from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from shared.contracts.agent import BehaviorPolicyConfig


# 表示工作时段数据
@dataclass(frozen=True)
class WorkPeriod:
    start: dt.time
    end: dt.time

    # 判断是否包含指定项
    def contains(self, value: dt.time) -> bool:
        if self.start <= self.end:
            return self.start <= value < self.end
        return value >= self.start or value < self.end


# 管理主动行为时间表
class BehaviorSchedule:
    # 初始化当前实例
    def __init__(self, timezone: str, periods: list[WorkPeriod]) -> None:
        self._timezone = ZoneInfo(timezone)
        self._periods = periods

    # 从配置创建实例
    @classmethod
    def from_config(cls, config: BehaviorPolicyConfig) -> "BehaviorSchedule":
        proactive = config.proactive
        periods = []
        for item in proactive.work_hours:
            periods.append(WorkPeriod(cls._time(item.start), cls._time(item.end)))
        return cls(proactive.timezone, periods)

    # 判断是否允许主动交互
    def allows_proactive(self, moment: dt.datetime | None = None) -> bool:
        if not self._periods:
            return False
        current = moment or dt.datetime.now(tz=self._timezone)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self._timezone)
        local_time = current.astimezone(self._timezone).time().replace(tzinfo=None)
        return any(period.contains(local_time) for period in self._periods)

    # 解析事件时间
    @staticmethod
    def _time(value: str) -> dt.time:
        hour, minute = (int(part) for part in value.split(":", 1))
        return dt.time(hour, minute)
