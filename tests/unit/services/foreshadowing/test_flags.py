"""伏線パッケージのフラグが既定OFFで、環境変数でONにできることの回帰テスト。"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from src.services.foreshadowing import flags

ALL = [
    "is_causal_dag_enabled", "is_anchor_snap_enabled",
    "is_relevance_injection_enabled", "is_cascade_reschedule_enabled",
    "is_short_horizon_enabled",
]

ENV_NAMES = [
    "FORESHADOW_CAUSAL_DAG", "FORESHADOW_ANCHOR_SNAP",
    "FORESHADOW_RELEVANCE_INJECTION", "FORESHADOW_CASCADE_RESCHEDULE",
    "FORESHADOW_SHORT_HORIZON",
]


def test_all_flags_default_off(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in ALL:
        assert getattr(flags, name)() is False, name


def test_truthy_values_enable(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("FORESHADOW_CAUSAL_DAG", raw)
        assert flags.is_causal_dag_enabled() is True, raw


def test_falsy_values_disable(monkeypatch):
    for raw in ("0", "false", "no", "off", "banana", ""):
        monkeypatch.setenv("FORESHADOW_CAUSAL_DAG", raw)
        assert flags.is_causal_dag_enabled() is False, raw


def test_top_k_clamped_to_non_negative(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "-5")
    assert flags.get_relevance_top_k() == 2
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "abc")
    assert flags.get_relevance_top_k() == 2
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "4")
    assert flags.get_relevance_top_k() == 4
