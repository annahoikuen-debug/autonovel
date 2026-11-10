"""RollupConfig の単体テスト (PLAN_M1 Step 3).

環境変数経由の設定読み込み、既定値、不正値フォールバックを検証する。
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from src.engine.context_compression.rollup_config import RollupConfig


class TestRollupConfigDefaults:
    """環境変数未設定時の既定値テスト。"""

    def test_defaults_all_false_or_sensible(self):
        """全フラグ False、数値は合理的な既定値。"""
        with patch.dict(os.environ, {}, clear=True):
            # 既存の関連 env をすべて削除
            for key in [
                "ENABLE_DIGEST_ROLLUP",
                "DIGEST_EPISODES_PER_BLOCK",
                "DIGEST_BLOCKS_PER_VOLUME",
                "ENABLE_PINNED_FACTS_EDGES",
                "DIGEST_COD_ROUNDS",
                "DIGEST_BLOCK_MAX_CHARS",
                "DIGEST_VOLUME_MAX_CHARS",
            ]:
                os.environ.pop(key, None)
            cfg = RollupConfig.from_env()
            assert cfg.rollup_enabled is False
            assert cfg.episodes_per_block == 10
            assert cfg.blocks_per_volume == 5
            assert cfg.pinned_edges_enabled is False
            assert cfg.cod_rounds == 1
            assert cfg.block_digest_chars == 300
            assert cfg.volume_digest_chars == 800

    def test_frozen_immutable(self):
        """dataclass(frozen=True) により属性書き換えが不可。"""
        cfg = RollupConfig.from_env()
        with pytest.raises(FrozenInstanceError):
            cfg.rollup_enabled = True  # type: ignore[misc]


class TestRollupConfigEnvOverride:
    """環境変数上書きテスト。"""

    @pytest.mark.parametrize(
        "env,key,expected",
        [
            ({"ENABLE_DIGEST_ROLLUP": "1"}, "rollup_enabled", True),
            ({"ENABLE_DIGEST_ROLLUP": "true"}, "rollup_enabled", True),
            ({"ENABLE_DIGEST_ROLLUP": "yes"}, "rollup_enabled", True),
            ({"ENABLE_DIGEST_ROLLUP": "on"}, "rollup_enabled", True),
            ({"ENABLE_DIGEST_ROLLUP": "0"}, "rollup_enabled", False),
            ({"ENABLE_DIGEST_ROLLUP": "false"}, "rollup_enabled", False),
            ({"DIGEST_EPISODES_PER_BLOCK": "20"}, "episodes_per_block", 20),
            ({"DIGEST_BLOCKS_PER_VOLUME": "3"}, "blocks_per_volume", 3),
            ({"ENABLE_PINNED_FACTS_EDGES": "1"}, "pinned_edges_enabled", True),
            ({"DIGEST_COD_ROUNDS": "2"}, "cod_rounds", 2),
            ({"DIGEST_BLOCK_MAX_CHARS": "500"}, "block_digest_chars", 500),
            ({"DIGEST_VOLUME_MAX_CHARS": "1200"}, "volume_digest_chars", 1200),
        ],
    )
    def test_env_override(self, env, key, expected):
        """環境変数が設定値に反映される。"""
        with patch.dict(os.environ, env, clear=True):
            # 他の関連 env をクリアして干渉を防ぐ
            for k in [
                "ENABLE_DIGEST_ROLLUP",
                "DIGEST_EPISODES_PER_BLOCK",
                "DIGEST_BLOCKS_PER_VOLUME",
                "ENABLE_PINNED_FACTS_EDGES",
                "DIGEST_COD_ROUNDS",
                "DIGEST_BLOCK_MAX_CHARS",
                "DIGEST_VOLUME_MAX_CHARS",
            ]:
                if k not in env:
                    os.environ.pop(k, None)
            cfg = RollupConfig.from_env()
            assert getattr(cfg, key) == expected, f"{key} should be {expected} with env={env}"


class TestRollupConfigInvalidFallback:
    """不正値・空値時のフォールバックテスト。"""

    @pytest.mark.parametrize(
        "env,key",
        [
            ({"DIGEST_EPISODES_PER_BLOCK": "not_a_number"}, "episodes_per_block"),
            ({"DIGEST_EPISODES_PER_BLOCK": ""}, "episodes_per_block"),
            ({"DIGEST_COD_ROUNDS": "abc"}, "cod_rounds"),
            ({"DIGEST_BLOCK_MAX_CHARS": "not_a_number"}, "block_digest_chars"),
        ],
    )
    def test_invalid_value_falls_back_to_default(self, env, key):
        """不正値や空値は既定値にフォールバックする。"""
        with patch.dict(os.environ, env, clear=True):
            for k in [
                "ENABLE_DIGEST_ROLLUP",
                "DIGEST_EPISODES_PER_BLOCK",
                "DIGEST_BLOCKS_PER_VOLUME",
                "ENABLE_PINNED_FACTS_EDGES",
                "DIGEST_COD_ROUNDS",
                "DIGEST_BLOCK_MAX_CHARS",
                "DIGEST_VOLUME_MAX_CHARS",
            ]:
                if k not in env:
                    os.environ.pop(k, None)
            cfg = RollupConfig.from_env()
            defaults = {
                "episodes_per_block": 10,
                "cod_rounds": 1,
                "block_digest_chars": 300,
            }
            assert getattr(cfg, key) == defaults[key], (
                f"{key} should fall back to {defaults[key]} with env={env}"
            )

    def test_cod_rounds_min_is_1(self):
        """cod_rounds は最低 1 (max(1, ...))。"""
        with patch.dict(os.environ, {"DIGEST_COD_ROUNDS": "0"}, clear=True):
            for k in [
                "ENABLE_DIGEST_ROLLUP",
                "DIGEST_EPISODES_PER_BLOCK",
                "DIGEST_BLOCKS_PER_VOLUME",
                "ENABLE_PINNED_FACTS_EDGES",
                "DIGEST_COD_ROUNDS",
                "DIGEST_BLOCK_MAX_CHARS",
                "DIGEST_VOLUME_MAX_CHARS",
            ]:
                if k != "DIGEST_COD_ROUNDS":
                    os.environ.pop(k, None)
            cfg = RollupConfig.from_env()
            assert cfg.cod_rounds == 1
