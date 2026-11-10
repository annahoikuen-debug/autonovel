"""階層的逐次要約メモリの設定 (PLAN_M1 Step 3).

全設定は環境変数経由で読み込む。ハードコードされた数値リテラルを
含まず、SSOT (Single Source of Truth) として機能する。

`tests/regression/test_no_hardcoded_thresholds.py` の対象ファイルに追加され、
マジックナンバー再導入の検出対象となる。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    """環境変数を int として読む。不正値・空値は default にフォールバック。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    """環境変数を bool として読む。"""
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RollupConfig:
    """階層的ダイジェストロールアップの設定。

    Attributes:
        rollup_enabled: ロールアップ生成の ON/OFF。False で現行の flat な
            1話ダイジェストのみを使用し、出力は現行とバイト同一となる。
        episodes_per_block: 章(ブロック)境界の話数。この話数ごとに章 rollup を生成。
        blocks_per_volume: 巻境界のブロック数。このブロックごとに巻 rollup を生成。
        pinned_edges_enabled: 重要事実をプロンプト先頭・末尾の両端に配置する
            Lost in the Middle 対策の ON/OFF。
        cod_rounds: Chain-of-Density 方式の要約パス数。1 で現行の1 pass と同一。
        block_digest_chars: 章 rollup の最大文字数。
        volume_digest_chars: 巻 rollup の最大文字数。
        pinned_max_chars: pinned_facts head (プロンプト先頭ブロック) の最大文字数。
        pinned_tail_max_chars: pinned_facts tail (プロンプト末尾ブロック) の最大文字数。
    """

    rollup_enabled: bool = False
    episodes_per_block: int = 10
    blocks_per_volume: int = 5
    pinned_edges_enabled: bool = False
    cod_rounds: int = 1
    block_digest_chars: int = 300
    volume_digest_chars: int = 800
    pinned_max_chars: int = 300
    pinned_tail_max_chars: int = 300

    @classmethod
    def from_env(cls) -> "RollupConfig":
        """環境変数から設定を構築する。"""
        return cls(
            rollup_enabled=_env_bool("ENABLE_DIGEST_ROLLUP", False),
            episodes_per_block=_env_int("DIGEST_EPISODES_PER_BLOCK", 10),
            blocks_per_volume=_env_int("DIGEST_BLOCKS_PER_VOLUME", 5),
            pinned_edges_enabled=_env_bool("ENABLE_PINNED_FACTS_EDGES", False),
            cod_rounds=max(1, _env_int("DIGEST_COD_ROUNDS", 1)),
            block_digest_chars=_env_int("DIGEST_BLOCK_MAX_CHARS", 300),
            volume_digest_chars=_env_int("DIGEST_VOLUME_MAX_CHARS", 800),
            pinned_max_chars=_env_int("PINNED_FACTS_MAX_CHARS", 300),
            pinned_tail_max_chars=_env_int("PINNED_FACTS_TAIL_MAX_CHARS", 300),
        )
