"""TRACK-C C1: 1話/監査フェーズ単位の LLM 呼出メトリクス.

`llm_calls_per_episode` / `llm_calls_audit_phase` が記録され、
`/metrics` (metrics_endpoint) に出力されることを検証する。

Prometheus レジストリはプロセス共通のため、テスト間でラベル値が
衝突しないようテスト毎に一意の episode_id を使用する。
"""

from __future__ import annotations

from src.backend.observability.metrics import (
    metrics_endpoint,
    record_audit_call,
    record_llm_call_per_episode,
)


async def _metrics_text() -> str:
    resp = await metrics_endpoint()
    return resp.body.decode("utf-8")


async def test_llm_calls_per_episode_recorded():
    """1話あたりの LLM 呼出が episode_id/model/tier ラベル付きで記録されること."""
    episode_id = "ep-per-001"
    record_llm_call_per_episode(episode_id=episode_id, model="gemini-1.5-pro", tier="tier1")
    record_llm_call_per_episode(episode_id=episode_id, model="gemini-1.5-pro", tier="tier1")

    text = await _metrics_text()
    # prometheus_client は Counter 名に _total を付与し、ラベルをアルファベット順に出力する
    expected = (
        'llm_calls_per_episode_total{episode_id="ep-per-001",model="gemini-1.5-pro",tier="tier1"} 2.0'
    )
    assert expected in text


async def test_audit_call_recorded():
    """監査呼び出しが episode_id/specialist/provider ラベル付きで記録されること."""
    episode_id = "ep-audit-001"
    record_audit_call(episode_id=episode_id, specialist="consistency", provider="gemini")

    text = await _metrics_text()
    expected = (
        'llm_calls_audit_phase_total{episode_id="ep-audit-001",provider="gemini",'
        'specialist="consistency"} 1.0'
    )
    assert expected in text


async def test_metrics_endpoint_outputs_llm_cost_metrics():
    """/metrics に llm_calls_* メトリクスの HELP/TYPE とサンプルが出力されること."""
    record_llm_call_per_episode(episode_id="ep-metrics-001", model="gpt-4o", tier="tier2")
    record_audit_call(episode_id="ep-metrics-001", specialist="factual", provider="openrouter")

    text = await _metrics_text()
    assert "# HELP llm_calls_per_episode_total" in text
    assert "# TYPE llm_calls_per_episode_total counter" in text
    assert "# HELP llm_calls_audit_phase_total" in text
    assert "# TYPE llm_calls_audit_phase_total counter" in text
    assert 'llm_calls_per_episode_total{episode_id="ep-metrics-001",model="gpt-4o",tier="tier2"} 1.0' in text
    assert (
        'llm_calls_audit_phase_total{episode_id="ep-metrics-001",provider="openrouter",'
        'specialist="factual"} 1.0'
    ) in text
