import logging
import threading
import time
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout: float = Field(default=30.0, gt=0.0)
    half_open_max_success: int = Field(default=1, ge=1)


class CircuitBreakerOpenException(Exception):
    """Exception raised when the circuit breaker is in OPEN state."""

    pass


class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        # 既定値を引数で評価すると全インスタンスで同一オブジェクトを共有してしまうため、
        # None を受けてインスタンスごとに生成する
        self.name = name
        self.config = config if config is not None else CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0.0
        # HALF_OPEN 状態で,in-flight のプローブ数
        self._half_open_probes = 0
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    logger.warning(
                        "[CircuitBreaker:%s] Transitioning from OPEN to HALF_OPEN",
                        self.name,
                    )
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self._half_open_probes = 0
                else:
                    return False
            if self.state == CircuitState.HALF_OPEN:
                # HALF_OPEN では同時実行の無制限なプローブを許さない
                # (さもないと half_open_max_success の上限が守られない)
                if self._half_open_probes >= self.config.half_open_max_success:
                    return False
                self._half_open_probes += 1
                return True
            return False

    def record_success(self):
        with self._lock:
            if self._half_open_probes > 0:
                self._half_open_probes -= 1
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.half_open_max_success:
                    logger.info(
                        "[CircuitBreaker:%s] Transitioning from HALF_OPEN to CLOSED",
                        self.name,
                    )
                    self._reset()
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self):
        with self._lock:
            if self._half_open_probes > 0:
                self._half_open_probes -= 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning(
                        "[CircuitBreaker:%s] Transitioning from CLOSED to OPEN (failures: %d)",
                        self.name,
                        self.failure_count,
                    )
                    self.state = CircuitState.OPEN
            elif self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    "[CircuitBreaker:%s] Transitioning from HALF_OPEN to OPEN (probe failed)",
                    self.name,
                )
                self.state = CircuitState.OPEN
                self.success_count = 0

    def _reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self._half_open_probes = 0
