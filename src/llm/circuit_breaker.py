from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderHealthState:
    provider_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: datetime | None = None
    opened_at: datetime | None = None
    success_count: int = 0
    # HALF_OPEN 状態で probe として既に電流が流れている呼び出し数。
    # success_count とは別に、cooldown 再評価を妨げないよう追跡する。
    probe_in_flight: int = 0
    last_error: str | None = None


class LLMCircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: float = 60.0,
        half_open_max_calls: int = 1,
        *,
        cooldown_seconds: float | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds cannot be negative")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")
        self.failure_threshold = failure_threshold
        self.timeout_seconds = float(timeout_seconds)
        self.cooldown_seconds = (
            float(timeout_seconds) if cooldown_seconds is None else float(cooldown_seconds)
        )
        self.half_open_max_calls = half_open_max_calls
        self._states: dict[str, ProviderHealthState] = {}
        self._lock = RLock()

    def get_state(self, provider_name: str) -> ProviderHealthState:
        with self._lock:
            if provider_name not in self._states:
                self._states[provider_name] = ProviderHealthState(provider_name)
            return self._states[provider_name]

    def can_execute(self, provider_name: str) -> bool:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        with self._lock:
            state = self.get_state(provider_name)
            if state.state is CircuitState.CLOSED:
                return True
            if state.state is CircuitState.OPEN:
                if (
                    state.opened_at is not None
                    and now - state.opened_at >= timedelta(seconds=self.cooldown_seconds)
                ):
                    state.state = CircuitState.HALF_OPEN
                    state.probe_in_flight = 0
                else:
                    return False
            if state.state is CircuitState.HALF_OPEN:
                # HALF_OPEN でも cooldown を再評価する。前回 here でしか評価していなかったため、
                # probe 結果が success/failure として記録されない経路（プロバイダ未解決、
                # 反対側のブレーカーで遮断、asyncio.CancelledError 等）を一度通ると
                # success_count が閾値に達したまま永不復帰になり latch していた。
                #
                # opened_at は「最後に probe を許可した時刻」をアンカーとして使い直すことで、
                # 「cooldown 経過ごとに 1 本だけ新しい probe を許可しつつ、
                #  同一ウィンドウ内の同時 probe は half_open_max_calls で制限する」
                # という通常の回路遮断 semantics を保つ。
                if (
                    state.opened_at is not None
                    and now - state.opened_at
                    >= timedelta(seconds=self.cooldown_seconds)
                ):
                    state.opened_at = now
                    state.probe_in_flight = 0
                if state.probe_in_flight >= self.half_open_max_calls:
                    return False
                state.probe_in_flight += 1
                return True
            return False

    def record_success(self, provider_name: str) -> None:
        with self._lock:
            state = self.get_state(provider_name)
            if state.probe_in_flight > 0:
                state.probe_in_flight -= 1
            if state.state is CircuitState.HALF_OPEN:
                state.state = CircuitState.CLOSED
                state.opened_at = None
                state.failure_count = 0
                state.success_count = 0
                state.probe_in_flight = 0
                state.last_error = None
                return
            if state.state is CircuitState.CLOSED:
                state.failure_count = 0
                state.success_count += 1
                state.last_error = None

    def record_failure(self, provider_name: str, error: Any = None) -> None:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        with self._lock:
            state = self.get_state(provider_name)
            state.last_failure_time = now
            state.last_error = str(error) if error is not None else state.last_error
            if state.probe_in_flight > 0:
                state.probe_in_flight -= 1
            if state.state is CircuitState.HALF_OPEN:
                state.state = CircuitState.OPEN
                state.opened_at = now
                state.probe_in_flight = 0
                state.success_count = 0
                return
            if state.state is CircuitState.CLOSED:
                state.failure_count += 1
                if state.failure_count >= self.failure_threshold:
                    state.state = CircuitState.OPEN
                    state.opened_at = now
                    state.probe_in_flight = 0

    def reset(self, provider_name: str | None = None) -> None:
        with self._lock:
            if provider_name is None:
                for state in self._states.values():
                    self._reset_state(state)
                return
            if provider_name in self._states:
                self._reset_state(self._states[provider_name])

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: self._serialize_state(state)
                for name, state in self._states.items()
            }

    @staticmethod
    def _reset_state(state: ProviderHealthState) -> None:
        state.state = CircuitState.CLOSED
        state.failure_count = 0
        state.opened_at = None
        state.success_count = 0
        state.probe_in_flight = 0
        state.last_error = None

    @staticmethod
    def _serialize_state(state: ProviderHealthState) -> dict[str, Any]:
        return {
            "provider_name": state.provider_name,
            "state": state.state.value,
            "failure_count": state.failure_count,
            "last_failure_time": (
                state.last_failure_time.isoformat()
                if state.last_failure_time is not None
                else None
            ),
            "opened_at": state.opened_at.isoformat() if state.opened_at is not None else None,
            "success_count": state.success_count,
            "probe_in_flight": state.probe_in_flight,
            "last_error": state.last_error,
        }
