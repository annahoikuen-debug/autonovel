"""M4-B: calibration_store テスト。

- yaml 読み込み
- 環境変数上書き (env > yaml > default)
- lru_cache キャッシュ
- 各種 getter 関数
- clear_cache
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.audit.calibration_store import (
    DEFAULT_CALIBRATION,
    clear_cache,
    get_calibration,
    get_cliche_max,
    get_evaluator_version,
    get_gate_threshold,
    get_weights,
    is_panel_enabled,
    is_pairwise_enabled,
)


def test_default_calibration():
    """デフォルト設定が正しい。"""
    assert DEFAULT_CALIBRATION["gate"]["absolute_threshold"] == 70.0
    assert DEFAULT_CALIBRATION["gate"]["cliche_max"] == 3
    assert DEFAULT_CALIBRATION["gate"]["weights"] == {"quantitative": 0.4, "qualitative": 0.6}


def test_load_yaml_config(tmp_path):
    """yaml ファイルを読み込む。"""
    yaml_path = tmp_path / "audit_calibration.yaml"
    yaml_path.write_text(
        """
gate:
  absolute_threshold: 75.0
  cliche_max: 5
  weights:
    quantitative: 0.5
    qualitative: 0.5
""",
        encoding="utf-8",
    )
    clear_cache()
    config = get_calibration(str(yaml_path))
    assert config["gate"]["absolute_threshold"] == 75.0
    assert config["gate"]["cliche_max"] == 5
    assert config["gate"]["weights"]["quantitative"] == 0.5
    assert config["gate"]["weights"]["qualitative"] == 0.5


def test_env_override_yaml(tmp_path, monkeypatch):
    """環境変数が yaml より優先される。"""
    yaml_path = tmp_path / "audit_calibration.yaml"
    yaml_path.write_text(
        "gate:\n  absolute_threshold: 75.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "85.0")
    clear_cache()
    config = get_calibration(str(yaml_path))
    assert config["gate"]["absolute_threshold"] == 85.0


def test_env_override_default(tmp_path, monkeypatch):
    """環境変数がデフォルトより優先される (yaml なし)。"""
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "90.0")
    clear_cache()
    config = get_calibration(str(tmp_path / "nonexistent.yaml"))
    assert config["gate"]["absolute_threshold"] == 90.0


def test_env_bool_override(tmp_path, monkeypatch):
    """環境変数の真偽値変換。"""
    yaml_path = tmp_path / "audit_calibration.yaml"
    yaml_path.write_text("pairwise:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("ENABLE_PAIRWISE", "true")
    clear_cache()
    config = get_calibration(str(yaml_path))
    assert config["pairwise"]["enabled"] is True

    monkeypatch.setenv("ENABLE_PAIRWISE", "false")
    clear_cache()
    config = get_calibration(str(yaml_path))
    assert config["pairwise"]["enabled"] is False


def test_get_gate_threshold():
    """get_gate_threshold が正しい値を返す。"""
    clear_cache()
    assert get_gate_threshold() == 70.0


def test_get_cliche_max():
    """get_cliche_max が正しい値を返す。"""
    clear_cache()
    assert get_cliche_max() == 3


def test_get_weights():
    """get_weights が (quantitative, qualitative) を返す。"""
    clear_cache()
    q, qual = get_weights()
    assert q == 0.4
    assert qual == 0.6


def test_is_pairwise_enabled():
    """is_pairwise_enabled が正しい値を返す。"""
    clear_cache()
    assert is_pairwise_enabled() is False


def test_is_panel_enabled():
    """is_panel_enabled が正しい値を返す。"""
    clear_cache()
    assert is_panel_enabled() is False


def test_get_evaluator_version():
    """get_evaluator_version が正しい値を返す。"""
    clear_cache()
    assert get_evaluator_version() == "1.0"


def test_cache_cleared_after_clear_cache(monkeypatch):
    """clear_cache 後に再読み込みされる。"""
    clear_cache()
    config1 = get_calibration()
    assert config1["gate"]["absolute_threshold"] == 70.0

    # 環境変数で変更
    monkeypatch.setenv("AUDIT_GATE_THRESHOLD", "99.0")
    clear_cache()
    config2 = get_calibration()
    assert config2["gate"]["absolute_threshold"] == 99.0

    monkeypatch.delenv("AUDIT_GATE_THRESHOLD", raising=False)
    clear_cache()
    config3 = get_calibration()
    assert config3["gate"]["absolute_threshold"] == 70.0
