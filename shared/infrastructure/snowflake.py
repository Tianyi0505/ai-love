
from __future__ import annotations

import threading
import time

from shared.infrastructure.runtime_config import ConfigKey, required_setting

EPOCH_MS = 1704067200000  # 2024-01-01T00:00:00Z

_SEQUENCE_BITS = 12
_WORKER_BITS = 10
_SEQUENCE_MASK = (1 << _SEQUENCE_BITS) - 1
_WORKER_MASK = (1 << _WORKER_BITS) - 1


# 生成雪花ID
class SnowflakeGenerator:
    def __init__(self, worker_id: int, epoch_ms: int = EPOCH_MS) -> None:
        self._worker = int(worker_id) & _WORKER_MASK
        self._epoch_ms = int(epoch_ms)
        self._sequence = 0
        self._last_ms = -1
        self._lock = threading.Lock()

    # 生成下一个ID
    def next_id(self) -> int:
        with self._lock:
            now = int(time.time() * 1000)
            if now < self._last_ms:
                now = self._last_ms
            if now == self._last_ms:
                self._sequence = (self._sequence + 1) & _SEQUENCE_MASK
                if self._sequence == 0:
                    now = self._wait_next_ms()
            else:
                self._sequence = 0
            self._last_ms = now
            return ((now - self._epoch_ms) << (_SEQUENCE_BITS + _WORKER_BITS)) | (
                self._worker << _SEQUENCE_BITS
            ) | self._sequence

    # 等待下一毫秒
    def _wait_next_ms(self) -> int:
        while True:
            now = int(time.time() * 1000)
            if now > self._last_ms:
                return now
            time.sleep(0.0005)


_instance: SnowflakeGenerator | None = None
_instance_lock = threading.Lock()


# 获取进程级生成器
def get_snowflake() -> SnowflakeGenerator:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                worker_id = int(required_setting(None, ConfigKey.AILOVE_SNOWFLAKE_WORKER_ID))
                _instance = SnowflakeGenerator(worker_id)
    return _instance


# 生成新ID字符串
def new_snowflake_id() -> str:
    return str(get_snowflake().next_id())


# 校验ID字符串
def is_snowflake_id(value) -> bool:
    if not isinstance(value, str) or not value.isdigit():
        return False
    return 0 < int(value) <= (1 << 63) - 1
