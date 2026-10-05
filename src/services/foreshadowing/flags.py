"""伏線パッケージの機能フラグ（W5 / PLAN_W5_CAUSAL_FORESIGHT_12STEPS Step 1）。

このパッケージは v5.3 まで環境変数を一切読んでおらず、段階導入の手段がなかった。
`FORESHADOW_*` の環境変数の出入口をこのファイルだけに集約する。

原則:
  - 公開APIはフラグ読み取り関数だけ（このファイルに副作用は書かない）
  - **すべて既定 False**。ON にしない限り既存挙動は完全に現状維持される
  - `settings` / pydantic を参照しない（`os.environ` のみ。テストは monkeypatch で操作）
"""
from __future__ import annotations

import os

#: 有効とみなす環境変数の値（小文字化・空白除去して比較する）
_TRUTHY = ("1", "true", "yes", "on")

#: 無効とみなす環境変数の値（上記以外はすべて無効。空文字も無効）
_FALSY = ("0", "false", "no", "off")

#: 関連度注入の既定上限件数
DEFAULT_RELEVANCE_TOP_K = 2


def _env_flag(name: str) -> bool:
    """環境変数 `name` が truthy なら True、それ以外（未設定含む）は False。"""
    raw = os.environ.get(name)
    if raw is None:
        return False
    value = raw.strip().lower()
    if value in _FALSY:
        return False
    return value in _TRUTHY


def is_causal_dag_enabled() -> bool:
    """因果DAG（Step 5, 6）の構築・利用を有効化する（既定 False）。"""
    return _env_flag("FORESHADOW_CAUSAL_DAG")


def is_anchor_snap_enabled() -> bool:
    """長期伏線を物語の節目（midpoint / climax）へ吸着させる（既定 False）。"""
    return _env_flag("FORESHADOW_ANCHOR_SNAP")


def is_short_horizon_enabled() -> bool:
    """短期ホライズン（planted + 3話以内）への丸めを有効化する（既定 False）。"""
    return _env_flag("FORESHADOW_SHORT_HORIZON")


def is_relevance_injection_enabled() -> bool:
    """プロンプトへ渡す背景伏線を関連度上位に限定する（既定 False）。"""
    return _env_flag("FORESHADOW_RELEVANCE_INJECTION")


def is_cascade_reschedule_enabled() -> bool:
    """延期時に依存する伏線も連鎖延期する（既定 False）。"""
    return _env_flag("FORESHADOW_CASCADE_RESCHEDULE")


def is_foreshadowing_planting_enabled() -> bool:
    """伏線自動設置（roadmap -> foreshadowings）を有効にするか（既定 False）。

    **既定 False**。このファイルの既定方針「ON にしない限り既存挙動は完全に
    現状維持される」に従い、OFF のままでは `plant_from_roadmap` は
    何もせず空リストを返し、DB への副作用もゼロになる（＝ロールバック可能）。
    """
    return _env_flag("FORESHADOW_PLANTING")


def get_relevance_top_k(default: int = DEFAULT_RELEVANCE_TOP_K) -> int:
    """関連度注入の上限件数（0 以上の整数のみ採用。不正値は `default`）。"""
    raw = os.environ.get("FORESHADOW_RELEVANCE_TOP_K")
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default
