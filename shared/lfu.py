from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class LFUState:
    counter: int
    last_decay_at: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> LFUState:
        return cls(counter=int(value["counter"]), last_decay_at=float(value["last_decay_at"]))

    def as_dict(self) -> dict[str, int | float]:
        return {"counter": self.counter, "last_decay_at": self.last_decay_at}


@dataclass(frozen=True)
class LFUConfig:
    decay_interval_sec: float
    log_factor: float
    log_offset: int
    max_counter: int
    score_counter_ceiling: int
    initial_counter: int


class LazyLFU:
    def __init__(
        self,
        config: LFUConfig,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self._random_value = random_value

    def initial(self, now: float, counter: int | None = None) -> LFUState:
        initial = self.config.initial_counter if counter is None else counter
        return LFUState(
            counter=min(self.config.max_counter, max(0, int(initial))),
            last_decay_at=now,
        )

    def age(self, state: LFUState, now: float) -> LFUState:
        elapsed = max(0.0, now - state.last_decay_at)
        periods = int(elapsed // self.config.decay_interval_sec)
        if periods == 0:
            return state
        return LFUState(
            counter=max(0, state.counter - periods),
            last_decay_at=state.last_decay_at + periods * self.config.decay_interval_sec,
        )

    def access(self, state: LFUState, now: float, hits: int = 1) -> LFUState:
        aged = self.age(state, now)
        counter = aged.counter
        for _ in range(max(0, hits)):
            if counter >= self.config.max_counter:
                break
            base = max(0, counter - self.config.log_offset)
            probability = 1.0 / (base * self.config.log_factor + 1.0)
            if self._random_value() < probability:
                counter += 1
        return LFUState(counter=counter, last_decay_at=aged.last_decay_at)

    def score(self, state: LFUState, now: float) -> float:
        aged = self.age(state, now)
        return min(1.0, aged.counter / self.config.score_counter_ceiling)

    def counter_for_score(self, score: float) -> int:
        return min(
            self.config.max_counter,
            max(0, round(score * self.config.score_counter_ceiling)),
        )

    def state_from_mapping(
        self,
        value: Mapping[str, object] | None,
        now: float,
        *,
        score: float | None = None,
    ) -> LFUState:
        if value:
            return LFUState.from_mapping(value)
        counter = None if score is None else self.counter_for_score(score)
        return self.initial(now, counter)
