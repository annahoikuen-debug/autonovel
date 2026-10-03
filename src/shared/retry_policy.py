from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_attempts: int = Field(default=3, ge=1)
    base_delay: float = Field(default=1.0, ge=0.0)
    max_delay: float = Field(default=30.0, ge=0.0)
    exponential_backoff: bool = True
    jitter: bool = True
    retryable_status_codes: tuple[int, ...] = Field(
        default_factory=lambda: (429, 500, 502, 503, 504)
    )

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculates the delay for the given attempt number (0-indexed).

        ジッターは max_delay でクランプした「後」に掛ける。そうしないと
        返り値が最大 1.5 * max_delay となり、保証されている上限を超える。
        """
        import random

        delay = self.base_delay
        if self.exponential_backoff and attempt > 0:
            delay = self.base_delay * (2**attempt)

        delay = min(delay, self.max_delay)

        if self.jitter:
            delay = delay * (0.5 + random.random())
            # ジッター適用後も上限を保証する
            delay = min(delay, self.max_delay)

        return delay
