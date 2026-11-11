"""audit_agent ゲート設定・閾値・環境変数ヘルパー。

src/agents/audit_agent.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit_agent.py`` は shim として残す。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TRUTHY = ("1", "true", "yes", "on")

#: スコア集約ゲートの既定 ON。``ENABLE_AUDIT_SCORE_GATE=false`` で
#: 従来の「1件でも失敗したら全文再執筆」にロールバックできる。
DEFAULT_ENABLE_AUDIT_SCORE_GATE = True

#: 従来の 5 監査（fast_screen / logical_consistency / deai / ability_consistency /
#: causal_integrity）を有効にするか。False の場合は UnifiedAuditor のみ
#: （1 LLM コール）を実行し、LLM 呼び出し回数を削減する。
#: ロールバック時は ``ENABLE_AUDIT_LEGACY_CORE=true`` とする。
DEFAULT_ENABLE_AUDIT_LEGACY_CORE = False

#: 総合スコアの下限閾値（0-100）。この値を下回るとき再執筆する。
#: ``UnifiedAuditor.audit`` の合否ライン（70.0）と揃えている。
DEFAULT_AUDIT_GATE_THRESHOLD = 70.0

#: Advisory（警告通過）帯の下限閾値（0-100, W4 Step 9）。
#: 「不合格だが致命でもない」状態（``AUDIT_GATE_ADVISORY_SEVERITIES`` のみが失敗し、
#: 総合スコアがこの値以上）を再執筆ではなく警告通過へ落とす。
DEFAULT_AUDIT_ADVISORY_THRESHOLD = 80.0

#: この severity の失敗だけは「警告で通す」帯に昇格してよい。
AUDIT_GATE_ADVISORY_SEVERITIES: tuple[str, ...] = ("medium", "low")

#: severity ごとの重み（全滅式ゲートでは区別されなかった重篤さの差）。
AUDIT_GATE_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 3.0,
    "high": 1.5,
    "medium": 1.0,
    "low": 0.5,
}

#: severity ごとの不合格時スコア（0-100）。
AUDIT_GATE_PENALTY_SCORE: dict[str, float] = {
    "critical": 0.0,
    "high": 30.0,
    "medium": 60.0,
    "low": 80.0,
}

#: 合格時のスコア。
AUDIT_GATE_PASS_SCORE = 100.0

#: 学習データの confidence_adjustment (-1.0 ~ 1.0) を何点へ換算するか。
AUDIT_GATE_CONFIDENCE_WEIGHT = 10.0

#: 学習調整（should_downgrade）による severity の降格表。
AUDIT_GATE_DOWNGRADE: dict[str, str] = {
    "critical": "high",
    "high": "medium",
    "medium": "low",
    "low": "low",
}

#: Advisory 緩和が「手動で上げた ``AUDIT_GATE_THRESHOLD``」を消さないためのガード。
#: 既定 ON。``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false`` で旧挙動へ戻せる。
DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD = True


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r を float に解釈できないため既定値 %s を使います", name, raw, default)
        return default


def is_score_gate_enabled() -> bool:
    """スコア集約ゲートが有効か（``ENABLE_AUDIT_SCORE_GATE``、既定 ON）。"""
    return _env_flag("ENABLE_AUDIT_SCORE_GATE", DEFAULT_ENABLE_AUDIT_SCORE_GATE)


def is_audit_legacy_core_enabled() -> bool:
    """従来の 5 監査を有効にするか（ロールバック用、既定 False）。

    False の場合は UnifiedAuditor のみ（1 LLM コール）を実行し、
    LLM 呼び出し回数を削減する。
    """
    return _env_flag("ENABLE_AUDIT_LEGACY_CORE", DEFAULT_ENABLE_AUDIT_LEGACY_CORE)


def get_gate_threshold() -> float:
    """再執筆を起こす総合スコアの閾値（``AUDIT_GATE_THRESHOLD``、既定 70.0）。"""
    return _env_float("AUDIT_GATE_THRESHOLD", DEFAULT_AUDIT_GATE_THRESHOLD)


def is_local_patch_enabled() -> bool:
    """再執筆時の局所パッチ優先（Step 25, ``ENABLE_AUDIT_LOCAL_PATCH``、既定 ON）。"""
    return _env_flag("ENABLE_AUDIT_LOCAL_PATCH", True)


def is_unified_auditor_blocking() -> bool:
    """UnifiedAuditor の verdict をゲート集計に含めるか（既定 False = 追加観測）。"""
    return _env_flag("ENABLE_AUDIT_UNIFIED_BLOCKING", False)


def is_span_patch_enabled() -> bool:
    """段落単位スパンパッチ（``ENABLE_AUDIT_SPAN_PATCH``、既定 ON, W4 Step 8）。"""
    return _env_flag("ENABLE_AUDIT_SPAN_PATCH", True)


def is_quote_patch_enabled() -> bool:
    """H8: 検証付き quote 置換パッチ（``ENABLE_AUDIT_QUOTE_PATCH``、既定 OFF）。

    OFF の場合は従来どおり ``actionable_patch`` を末尾追記する。
    ON の場合は ``original_quote`` 必須の置換を先に試行し、不成立なら
    従来の追記へフォールバックする。
    """
    return _env_flag("ENABLE_AUDIT_QUOTE_PATCH", False)


def is_lesson_enabled() -> bool:
    """H8: 教訓メモリ（``ENABLE_AUDIT_LESSONS``、既定 OFF）。

    OFF の場合は教訓の記録・注入を行わず、現行挙動とバイト同一にする。
    """
    return _env_flag("ENABLE_AUDIT_LESSONS", False)


def get_lesson_active_max() -> int:
    """book あたり active 教訓の上限（``AUDIT_LESSON_ACTIVE_MAX``、既定 20）。"""
    return _env_int("AUDIT_LESSON_ACTIVE_MAX", 20)


def get_lesson_inject_max_items() -> int:
    """注入する教訓の最大件数（``AUDIT_LESSON_INJECT_MAX_ITEMS``、既定 5）。"""
    return _env_int("AUDIT_LESSON_INJECT_MAX_ITEMS", 5)


def get_lesson_block_max_chars() -> int:
    """注入ブロック全体の最大文字数（``AUDIT_LESSON_BLOCK_MAX_CHARS``、既定 800）。"""
    return _env_int("AUDIT_LESSON_BLOCK_MAX_CHARS", 800)


def get_lesson_max_chars() -> int:
    """教訓 1 件の最大文字数（``AUDIT_LESSON_MAX_CHARS``、既定 200）。"""
    return _env_int("AUDIT_LESSON_MAX_CHARS", 200)


def get_lesson_min_occurrences() -> int:
    """注入に必要な最小発生回数（``AUDIT_LESSON_MIN_OCCURRENCES``、既定 1）。"""
    return _env_int("AUDIT_LESSON_MIN_OCCURRENCES", 1)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r を int に解釈できないため既定値 %s を使います", name, raw, default)
        return default


def is_async_polish_enabled() -> bool:
    """検証付き ``polish_span`` の利用（``ENABLE_AUDIT_POLISH_ASYNC``、既定 ON, W4 Step 8）。"""
    return _env_flag("ENABLE_AUDIT_POLISH_ASYNC", True)


def is_repair_budget_enabled() -> bool:
    """全滅再生成の予算封じ込め（``ENABLE_AUDIT_REPAIR_BUDGET``、既定 ON, W4 Step 10）。"""
    return _env_flag("ENABLE_AUDIT_REPAIR_BUDGET", True)


def get_advisory_threshold() -> float:
    """警告通過帯の下限閾値（``AUDIT_ADVISORY_THRESHOLD``、既定 80.0, W4 Step 9）。"""
    return _env_float("AUDIT_ADVISORY_THRESHOLD", DEFAULT_AUDIT_ADVISORY_THRESHOLD)


def is_advisory_strict_guard_enabled() -> bool:
    """手動の厳格化（``AUDIT_GATE_THRESHOLD`` 上昇）で advisory 緩和を止めるガード（既定 ON）。

    ``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false`` で無効化できる。
    """
    return _env_flag("ENABLE_AUDIT_ADVISORY_STRICT_GUARD", DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD)
