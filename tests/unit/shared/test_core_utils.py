"""src/shared/network.py / event_bus.py / result.py / retry_policy.py の単体テスト."""
from __future__ import annotations

import importlib

import pytest

from src.shared.network import NetworkUtils
from src.shared.event_bus import UIEventType
from src.shared.result import Result
from src.shared.retry_policy import RetryPolicy


class TestNetworkUtils:
    def test_generate_connection_id_unique(self):
        a = NetworkUtils.generate_connection_id()
        b = NetworkUtils.generate_connection_id()
        assert a != b
        assert isinstance(a, str)
        assert len(a) == 36


class TestUIEventType:
    def test_values(self):
        assert UIEventType.REQUEST_GENERATE_PLAN == "REQUEST_GENERATE_PLAN"
        assert UIEventType.REQUEST_AUDIT_PLAN == "REQUEST_AUDIT_PLAN"
        assert UIEventType.REQUEST_GENERATE_EPISODE == "REQUEST_GENERATE_EPISODE"
        assert UIEventType.REQUEST_CANCEL_JOB == "REQUEST_CANCEL_JOB"

    def test_is_str_subclass(self):
        assert isinstance(UIEventType.REQUEST_CANCEL_JOB, str)


class TestResult:
    def test_ok(self):
        r = Result.ok(3)
        assert r.is_ok and not r.is_err
        assert r.unwrap() == 3

    def test_err(self):
        e = ValueError("bad")
        r = Result.err(e)
        assert r.is_err and not r.is_ok
        with pytest.raises(ValueError):
            r.unwrap()

    def test_map_ok(self):
        assert Result.ok(2).map(lambda x: x * 3).unwrap() == 6

    def test_map_err_propagates(self):
        r: Result[int, ValueError] = Result.err(ValueError("x"))
        out = r.map(lambda v: v + 1)
        assert out.is_err
        assert isinstance(out.error, ValueError)

    def test_map_err_ok_passthrough(self):
        r: Result[int, ValueError] = Result.ok(5)
        out = r.map_err(lambda e: e)
        assert out.is_ok and out.value == 5

    def test_map_err_transforms(self):
        r: Result[int, ValueError] = Result.err(ValueError("x"))
        out = r.map_err(lambda e: ValueError("y"))
        assert isinstance(out.error, ValueError)
        assert str(out.error) == "y"


class TestRetryPolicy:
    def test_defaults_and_frozen(self):
        p = RetryPolicy()
        assert p.max_attempts == 3
        assert p.retryable_status_codes == (429, 500, 502, 503, 504)
        with pytest.raises(Exception):
            p.max_attempts = 9  # type: ignore[misc]

    def test_calculate_delay_no_backoff_no_jitter(self):
        p = RetryPolicy(base_delay=2.0, exponential_backoff=False, jitter=False, max_delay=100.0)
        assert p.calculate_delay(0) == 2.0
        assert p.calculate_delay(5) == 2.0

    def test_calculate_delay_exponential_capped(self):
        p = RetryPolicy(base_delay=1.0, exponential_backoff=True, jitter=False, max_delay=4.0)
        assert p.calculate_delay(0) == 1.0
        assert p.calculate_delay(1) == 2.0
        assert p.calculate_delay(9) == 4.0

    def test_calculate_delay_jitter_bounds(self):
        p = RetryPolicy(base_delay=1.0, exponential_backoff=False, jitter=True)
        for _ in range(20):
            d = p.calculate_delay(0)
            assert 0.5 <= d <= 1.5


def test_result_module_reimport_stable():
    mod = importlib.import_module("src.shared.result")
    assert mod.Result is Result
