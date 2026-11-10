"""PLAN_S1 N6 の回帰テスト — narrative_structure 設定の SSOT 契約。

壊れ方: ハードコード再導入 / 未知 mode が例外 / 既定値変更 /
env と yaml の優先順位逆転 → このテストが赤になる。
(改善 #9 M4「ハードコード再導入防止」パターンの構造ゲート版)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.engine.structure_gate import (
    DEFAULT_SETTINGS,
    ENV_MODE_KEY,
    VALID_MODES,
    load_settings,
    reset_settings_cache,
)

SRC_GATE = Path("src/engine/structure_gate.py")
CONFIG_YAML = Path("config/narrative_structure.yaml")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """各テストで env の影響を排除する。"""
    monkeypatch.delenv(ENV_MODE_KEY, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


class TestDefaultContract:
    def test_default_is_off(self):
        """既定 (yaml・env とも未指定) が off であること (P1 / F1B P4 踏襲)。"""
        assert load_settings().mode == "off"

    def test_yaml_values_are_the_ssot(self):
        """リポジトリ yaml の値が loader 経由で取得できること。"""
        settings = load_settings()
        assert settings.max_step_delta == 4.0
        assert settings.rolling_min_sum == 6.0
        assert settings.rolling_window == 3
        assert settings.beat_type_mapping["Friction"] == "SETUP"
        # P6: 上書き禁止フィールドに tension は含まれない (補正対象であるため)
        assert "tension" not in settings.enforce_overwrite_forbidden

    def test_code_defaults_match_yaml(self):
        """コード内デフォルトと yaml の齟齬がないこと (yaml 欠落時の挙動保証)。"""
        assert DEFAULT_SETTINGS["mode"] == "off"
        assert DEFAULT_SETTINGS["max_step_delta"] == 4.0
        assert DEFAULT_SETTINGS["rolling_min_sum"] == 6.0

    def test_yaml_file_exists_and_quotes_mode(self):
        """yaml が存在し、mode がクォート済み (YAML 1.1 ブール化防止) であること。"""
        assert CONFIG_YAML.exists()
        assert 'mode: "off"' in CONFIG_YAML.read_text(encoding="utf-8")


class TestModeResolution:
    def test_valid_modes(self):
        assert VALID_MODES == ("off", "warn", "enforce")

    def test_unknown_mode_falls_back_to_off(self, tmp_path):
        """未知の mode 値は off に倒すこと (get_spine_quality パターン踏襲)。"""
        config = tmp_path / "ns.yaml"
        config.write_text('mode: "typo"', encoding="utf-8")
        assert load_settings(config_path=str(config)).mode == "off"

    def test_bare_off_in_yaml_is_parsed_as_off(self, tmp_path):
        """YAML 1.1 が off をブールにパースしても off に倒れること。"""
        config = tmp_path / "ns.yaml"
        config.write_text("mode: off\n", encoding="utf-8")
        assert load_settings(config_path=str(config)).mode == "off"

    def test_env_overrides_yaml(self, monkeypatch, tmp_path):
        """優先順位: env > yaml (N6 契約)。"""
        config = tmp_path / "ns.yaml"
        config.write_text('mode: "warn"', encoding="utf-8")
        monkeypatch.setenv(ENV_MODE_KEY, "enforce")
        assert load_settings(config_path=str(config)).mode == "enforce"

    def test_env_invalid_value_falls_back_to_off(self, monkeypatch, tmp_path):
        """env に無効値があっても例外にせず off に倒すこと。"""
        config = tmp_path / "ns.yaml"
        config.write_text('mode: "warn"', encoding="utf-8")
        monkeypatch.setenv(ENV_MODE_KEY, "typo")
        assert load_settings(config_path=str(config)).mode == "off"

    def test_missing_yaml_uses_defaults(self, tmp_path):
        """yaml 欠落時もデフォルトで継続すること (fail-open)。"""
        assert load_settings(config_path=str(tmp_path / "missing.yaml")).mode == "off"


class TestNoHardcodedThresholds:
    def test_detection_uses_ssot_constants_not_literals(self):
        """detect_tension_violations が制約定数を SSOT から取得すること。

        関数本体に max_step_delta / rolling_min_sum の値 (4, 6, 40, 60 等) が
        リテラルで現れたら、SSOT 変更がゲート判定に反映されなくなる (N6 違反)。
        """
        tree = ast.parse(SRC_GATE.read_text(encoding="utf-8"))
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "detect_tension_violations":
                target = node
                break
        assert target is not None, "detect_tension_violations が見つからない"

        literals = {
            node.value
            for node in ast.walk(target)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
        }
        # 許容するのはインデックス算出の 0 / 1 のみ (float 表記も含む)
        forbidden = {lit for lit in literals if lit not in (0, 1, 0.0, 1.0)}
        assert forbidden == set(), f"SSOT を経由しない数値リテラル: {forbidden}"

    def test_ssot_change_changes_detection(self):
        """SSOT の定数変更が検出結果に反映されること (SSOT が効いていることの実証)。"""
        from src.engine.structure_gate import NarrativeStructureSettings, detect_tension_violations
        from src.narrative_balancer import Beat

        beats = [Beat(episode=1, tension=2.0), Beat(episode=2, tension=6.5)]
        assert len(detect_tension_violations(beats, NarrativeStructureSettings(max_step_delta=4.0))) == 1
        assert detect_tension_violations(beats, NarrativeStructureSettings(max_step_delta=5.0)) == []
