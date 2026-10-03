# src/agents/audit_agent.py
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from src.agents.skill_base import SkillAgent
from src.agents.orchestrator import AgentContext, AgentResult, AgentName
from src.agents.audit import (
    LogicalAuditor,
    DeAIAuditor,
    FastPlotScreener,
    AbilityConsistencyChecker,
    PlotIntegrityMonitor,
)
from src.audit.repair_planner import plan_repair
from src.audit.static_rules import StaticRuleAuditor
from src.generation.pdca_controller import PDCAController
from src.services.learning_data_service import LearningDataService

logger = logging.getLogger(__name__)

_TRUTHY = ("1", "true", "yes", "on")

# ---------------------------------------------------------------------------
# 判定項目の棚卸し（Step 23: UnifiedAuditor 統合時も 1対1 で維持する）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditCriterion:
    """監査1件を表す不変レコード。

    ``audit_id`` はイベント追跡用の安定 ID（Step 21）。
    ``severity`` は「不合格했을 때の重篤さ」で、ゲート集約の重み付けに使う。
    ``learning_key`` は ``_check_learning_adjustment`` に渡す学習データキー。
    ``blocking`` は False のときゲート判定の集計対象から外れる
    （UnifiedAuditor は LLM 未設定時に fail-closed するため、
    本番未設定veter无意中全話不合格にしないよう既定 False とする）。
    """

    audit_id: str
    label: str
    severity: str
    learning_key: str
    blocking: bool = True


#: 既存5監査（変更禁止）。UnifiedAuditor 統合は本リストを変更せず追加で行う。
CORE_AUDIT_CRITERIA: tuple[AuditCriterion, ...] = (
    AuditCriterion(
        audit_id="fast_screen",
        label="プロット高速スクリーニング",
        severity="high",
        learning_key="fast_screen",
    ),
    AuditCriterion(
        audit_id="logical_consistency",
        label="論理整合性監査",
        severity="high",
        learning_key="logical_consistency",
    ),
    AuditCriterion(
        audit_id="deai",
        label="AI感除去監査（DeAI）",
        severity="medium",
        learning_key="deai",
    ),
    AuditCriterion(
        audit_id="ability_consistency",
        label="能力整合性チェック",
        severity="medium",
        learning_key="ability_consistency",
    ),
    AuditCriterion(
        audit_id="causal_integrity",
        label="プロット整合性モニター（因果律）",
        severity="high",
        learning_key="causal_integrity",
    ),
)

#: UnifiedAuditor（定性的判断フェーズ, v6-A2）。既存5監査とは独立した第6の観点で、
#: 既存判定項目を置き換えずに「追加」する。
UNIFIED_AUDIT_CRITERION = AuditCriterion(
    audit_id="unified_qualitative",
    label="定性的判断（UnifiedAuditor 統合）",
    severity="medium",
    learning_key="unified_qualitative",
    blocking=False,
)

AUDIT_CRITERIA: tuple[AuditCriterion, ...] = CORE_AUDIT_CRITERIA + (UNIFIED_AUDIT_CRITERION,)

# ---------------------------------------------------------------------------
# ゲート設定（Step 23: 全滅式ゲート → スコア集約式ゲート）
# ---------------------------------------------------------------------------

#: スコア集約ゲートの既定 ON。``ENABLE_AUDIT_SCORE_GATE=false`` で
#: 従来の「1件でも失敗したら全文再執筆」にロールバックできる。
DEFAULT_ENABLE_AUDIT_SCORE_GATE = True

#: 総合スコアの下限閾値（0-100）。この値を下回只有在とき再執筆する。
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


def is_async_polish_enabled() -> bool:
    """検証付き ``polish_span`` の利用（``ENABLE_AUDIT_POLISH_ASYNC``、既定 ON, W4 Step 8）。"""
    return _env_flag("ENABLE_AUDIT_POLISH_ASYNC", True)


def is_repair_budget_enabled() -> bool:
    """全滅再生成の予算封じ込め（``ENABLE_AUDIT_REPAIR_BUDGET``、既定 ON, W4 Step 10）。"""
    return _env_flag("ENABLE_AUDIT_REPAIR_BUDGET", True)


def get_advisory_threshold() -> float:
    """警告通過帯の下限閾値（``AUDIT_ADVISORY_THRESHOLD``、既定 80.0, W4 Step 9）。"""
    return _env_float("AUDIT_ADVISORY_THRESHOLD", DEFAULT_AUDIT_ADVISORY_THRESHOLD)


#: Advisory 緩和が「手動で上げた ``AUDIT_GATE_THRESHOLD``」を消さないためのガード。
#: 既定 ON。``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false`` で旧挙動へ戻せる。
DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD = True


def is_advisory_strict_guard_enabled() -> bool:
    """手動の厳格化（``AUDIT_GATE_THRESHOLD`` 上昇）で advisory 緩和を止めるガード（既定 ON）。

    ``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false`` で無効化できる。
    """
    return _env_flag(
        "ENABLE_AUDIT_ADVISORY_STRICT_GUARD", DEFAULT_ENABLE_AUDIT_ADVISORY_STRICT_GUARD
    )


def evaluate_gate(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """5監査を 0-100 に正規化し、severity 重み＋学習調整で集約する（モジュールヘルパ）。

    Args:
        outcomes: ``run_audit_phase`` が返す outcome 辞書の一覧

    Returns:
        ``mode`` / ``aggregate_score`` / ``threshold`` / ``requires_regeneration``
        / ``critical_failure`` / ``scored_audit_ids`` を含む辞書。
    """
    threshold = get_gate_threshold()
    blocking = [o for o in outcomes if o["blocking"]]
    scored = blocking or outcomes

    weighted_sum = sum(o["score"] * o["weight"] for o in scored)
    weight_total = sum(o["weight"] for o in scored)
    aggregate = (weighted_sum / weight_total) if weight_total else AUDIT_GATE_PASS_SCORE

    critical_failure = any(o["effective_severity"] == "critical" for o in scored)
    failed = [o for o in outcomes if not o["passed"]]

    if is_score_gate_enabled():
        requires_regeneration = bool(failed) and (aggregate < threshold or critical_failure)
        mode = "score_aggregation"
    else:
        # ロールバック: 従来の全滅式ゲート
        requires_regeneration = bool(failed)
        mode = "all_or_nothing"

    # W4 Step 9: Advisory（警告通過）帯。
    # 「不合格だが致命でもない」= failed の effective_severity がすべて
    # AUDIT_GATE_ADVISORY_SEVERITIES に含まれ、かつ総合スコアが
    # advisory_threshold 以上のときだけ再執筆を警告通過へ落とす。
    #
    # 帯は ``advisory_threshold < threshold`` のときだけ有効（= aggregate が
    # [advisory_threshold, threshold) に落ちる場合だけ relief する）。これにより
    # 意図的に上げた ``AUDIT_GATE_THRESHOLD``（= 手動の厳格化）が
    # advisory に上書きされて取り消される事故を防ぐ。
    #
    # W4 Step 11 実バグB: 上記ガードだけでは ``AUDIT_GATE_THRESHOLD`` を
    # 手動で上げた場合（例: 99.0）既定 advisory（80.0）との大小関係Established
    # ``80 < 99`` となり、緩和が発火して「再執筆する」が「警告通過」に反転していた。
    # 緩和は「threshold が既定値 ``DEFAULT_AUDIT_GATE_THRESHOLD`` のまま」のとき
    # だけ許可し、手動の厳格化があれば緩和しない。
    # 無効化は ``ENABLE_AUDIT_ADVISORY_STRICT_GUARD=false``。
    advisory = False
    advisory_reason = ""
    strict_guard = (
        is_advisory_strict_guard_enabled()
        and threshold > DEFAULT_AUDIT_GATE_THRESHOLD
        and get_advisory_threshold() == DEFAULT_AUDIT_ADVISORY_THRESHOLD
    )
    if (
        mode == "score_aggregation"
        and requires_regeneration
        and not critical_failure
        and failed
        and not strict_guard
        and get_advisory_threshold() < threshold
        and aggregate >= get_advisory_threshold()
        and all(
            (o.get("effective_severity") in AUDIT_GATE_ADVISORY_SEVERITIES) for o in failed
        )
    ):
        advisory_threshold = get_advisory_threshold()
        requires_regeneration = False
        advisory = True
        advisory_reason = (
            f"総合スコア {round(aggregate, 2)} が advisory 閾値 "
            f"{advisory_threshold} 以上かつ失敗は "
            f"{'/'.join(AUDIT_GATE_ADVISORY_SEVERITIES)} のみのため警告通過"
        )

    return {
        "mode": mode,
        "aggregate_score": round(aggregate, 2),
        "threshold": threshold,
        "requires_regeneration": requires_regeneration,
        "critical_failure": critical_failure,
        "failed_count": len(failed),
        "scored_audit_ids": [o["audit_id"] for o in scored],
        "advisory": advisory,
        "advisory_reason": advisory_reason,
    }


class AuditAgent(SkillAgent):
    """品質監査を担当するエージェント（ファサード）。
    既存の複数の監査クラスを統合し、統一インターフェースを提供する。
    学習データ（ネガティブサンプル）を活用して監査精度を動的に調整する。

    v6 / Step 21: 5監査を ``asyncio.gather(..., return_exceptions=True)`` で
    並列化し、``audit_id`` 付きでイベントを発火、監査フェーズのレイテンシを
    ``time.perf_counter()`` で計測する。
    v6 / Step 23: 全滅式ゲートをスコア集約式ゲートへ変更し、
    ``UnifiedAuditor`` を定性的判断フェーズに統合する。
    v6 / Step 25: 再執筆前に局所パッチ（SafeReplacer / actionable_patch /
    LocalPolisher）を試し、適用できない場合のみ全文再執筆へフォールバックする。
    """

    def __init__(
        self,
        repo: Any = None,
        llm: Any = None,
        prompt_manager: Any = None,
        edge_preserver: Any = None,
        audit_llm: Any = None,
        unified_auditor: Any = None,
        **kwargs,
    ):
        super().__init__(repo=repo, llm=llm)
        self.prompt_manager = prompt_manager

        # 内部監査コンポーネントを初期化
        self._logical_auditor = LogicalAuditor(
            repo=repo, llm=llm, pm=prompt_manager, generate_json=llm
        )
        self._deai_auditor = DeAIAuditor(
            repo=repo, llm=llm, prompt_manager=prompt_manager, edge_preserver=edge_preserver
        )
        self._fast_screener = FastPlotScreener(llm=llm, prompt_manager=prompt_manager)
        self._ability_checker = AbilityConsistencyChecker(llm=llm, prompt_manager=prompt_manager)
        self._plot_monitor = PlotIntegrityMonitor()

        # 学習データサービス
        self._learning_service = LearningDataService(repo=repo)

        # 定性的判断フェーズ用の LLM（無ければ執筆用 LLM を流用）
        self._audit_llm = audit_llm if audit_llm is not None else llm
        self._unified_auditor = unified_auditor
        self._unified_auditor_resolved = unified_auditor is not None

        #: 直近1回の監査フェーズレイテンシ（秒, time.perf_counter 基準）
        self.last_audit_latency_seconds: float | None = None
        #: 直近1回の監査フェーズのうち、各 audit_id の所要時間（秒）
        self.last_audit_durations: dict[str, float] = {}
        #: 直近1回のゲート判定結果
        self.last_gate_evaluation: dict[str, Any] | None = None
        #: 直近1回の UnifiedAuditor レポート（パッチ抽出に使う）
        self.last_unified_report: Any = None
        self._emitted_events: list[dict[str, Any]] = []

        # W4 Step 10: 全滅（Branch D）再生成の予算。1話につき1回だけ許可する。
        # 2回目以降は「パッチ出来なかった → 警告通過」側へ落とす。
        self._repair_budget = PDCAController(max_regenerations=1, max_local_patches=3)

    # ------------------------------------------------------------------
    # イベント
    # ------------------------------------------------------------------

    def emit_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """イベント発行（呼び出し履歴も保持し、追跡を契約テストで保証する）。"""
        self._emitted_events.append({"event": event_name, **payload})
        if len(self._emitted_events) > 500:
            del self._emitted_events[:-500]
        super().emit_event(event_name, payload)

    def drain_events(self) -> list[dict[str, Any]]:
        """このエージェントが発火済みイベントを取り出してクリアする。"""
        events = list(self._emitted_events)
        self._emitted_events.clear()
        return events

    # ------------------------------------------------------------------
    # 学習調整
    # ------------------------------------------------------------------

    async def _check_learning_adjustment(
        self, audit_type: str, field_path: str | None = None
    ) -> tuple[bool, float]:
        """学習データに基づく監査調整をチェック

        Returns:
            (should_downgrade, confidence_adjustment)
            - should_downgrade: True の場合、この監査失敗を warning 扱いにして auto-retry しない
            - confidence_adjustment: 信頼度調整値 (-1.0 ~ 1.0)
        """
        if self.repo is None:
            return False, 0.0

        try:
            return await self._learning_service.should_skip_audit_type(audit_type, field_path)
        except Exception:
            # 学習サービスエラーは無視してデフォルト動作
            return False, 0.0

    # ------------------------------------------------------------------
    # 個別監査（Step 21: 並列化の単位）
    # ------------------------------------------------------------------

    async def _run_core_audits(
        self,
        writing_context: dict[str, Any],
        drafted_text: str,
        book_id: int,
        ep_num: int,
        branch_id: int | None = None,
    ) -> list[tuple[AuditCriterion, Any]]:
        """既存5監査を投入し、``(criterion, 結果)`` のリストを返す。

        各要素は coroutine_factory（呼び出すと coroutine を返す）。
        入力は互いに独立しているため Step 21 で ``asyncio.gather`` に並列化できる。
        """
        blueprint = writing_context.get("plot", {}).get("detailed_blueprint", "")
        edges = writing_context.get("sharp_edges", [])
        emotional_hook = writing_context.get("emotional_hook")
        settings_json = writing_context.get("world_settings", "{}")
        chars_json = writing_context.get("characters_json", "[]")

        criteria = list(CORE_AUDIT_CRITERIA)

        if not blueprint:
            # fast_screen は blueprint が無いと判定できない（従来どおりスキップ＝合格扱い）
            criteria = [c for c in criteria if c.audit_id != "fast_screen"]

        async def _fast_screen() -> tuple[bool, str]:
            return await self._fast_screener.screen_plot(blueprint)

        async def _logical() -> tuple[bool, str, float]:
            return await self._logical_auditor.audit_logical_consistency(
                book_id=book_id, ep_num=ep_num, blueprint=blueprint, branch_id=branch_id
            )

        async def _deai() -> tuple[bool, str]:
            return await self._deai_auditor.audit(
                content=drafted_text,
                before_content=writing_context.get("prev_ctx", ""),
                edges=edges,
                emotional_hook=emotional_hook,
            )

        async def _ability() -> tuple[bool, str, str]:
            return await self._ability_checker.audit_ability_consistency(
                blueprint=drafted_text, settings_json=settings_json, characters_json=chars_json
            )

        async def _causal() -> tuple[bool, float, Any]:
            keywords = await self._plot_monitor.extract_keywords(drafted_text)
            return await self._plot_monitor.check_integrity(
                keywords=keywords,
                blueprint=blueprint,
                content=drafted_text,
                threshold=0.7,
            )

        factories = {
            "fast_screen": _fast_screen,
            "logical_consistency": _logical,
            "deai": _deai,
            "ability_consistency": _ability,
            "causal_integrity": _causal,
        }
        return [(c, factories[c.audit_id]) for c in criteria]

    async def _run_unified_auditor(
        self, writing_context: dict[str, Any], drafted_text: str
    ) -> tuple[AuditCriterion, Any]:
        """UnifiedAuditor による定性的判断（v6-A2）。

        LLM が未設定の場合は「評価不成立（degraded）」を返し、
        既定ではゲート集計の外側（追加観測）に留める。
        """
        criterion = UNIFIED_AUDIT_CRITERION
        auditor = self._resolve_unified_auditor()
        if auditor is None:
            return criterion, ("degraded", "UnifiedAuditor に LLM が設定されていません")
        try:
            report = await auditor.audit(
                text=drafted_text,
                character_profiles=str(writing_context.get("characters_json", "")),
                plot_spec=str(writing_context.get("plot", {}).get("detailed_blueprint", "")),
            )
        except Exception as exc:
            return criterion, ("degraded", f"UnifiedAuditor 実行失敗: {exc}")
        self.last_unified_report = report
        return criterion, report

    def _resolve_unified_auditor(self) -> Any:
        """UnifiedAuditor を遅延生成する（LLM 未設定なら ``None``）。"""
        if self._unified_auditor_resolved:
            return self._unified_auditor
        self._unified_auditor_resolved = True
        if self._audit_llm is None:
            self._unified_auditor = None
            return None
        try:
            from src.agents.specialists.unified_auditor import UnifiedAuditor

            self._unified_auditor = UnifiedAuditor(llm_gateway=self._audit_llm)
        except Exception:
            logger.warning("UnifiedAuditor の初期化に失敗しました", exc_info=True)
            self._unified_auditor = None
        return self._unified_auditor

    # ------------------------------------------------------------------
    # 判定結果の正規化
    # ------------------------------------------------------------------

    async def _to_outcome(self, criterion: AuditCriterion, raw: Any) -> dict[str, Any]:
        """監査結果を 0-100 正規化可能な共通 outcome 辞書へ変換する。"""
        if criterion.audit_id == "unified_qualitative":
            return self._unified_to_outcome(criterion, raw)
        return await self._core_to_outcome(criterion, raw)

    async def _core_to_outcome(self, criterion: AuditCriterion, raw: Any) -> dict[str, Any]:
        passed, feedback, *rest = raw
        feedback_text = "" if feedback is None else str(feedback)
        detail: dict[str, Any] = {}
        if rest:
            detail["raw"] = rest[0]

        if passed:
            return {
                "audit_id": criterion.audit_id,
                "label": criterion.label,
                "passed": True,
                "feedback": feedback_text,
                "severity": criterion.severity,
                "learning_adjusted": False,
                "confidence_adjustment": 0.0,
                "effective_severity": None,
                "error": None,
                "score": AUDIT_GATE_PASS_SCORE,
                "weight": 1.0,
                "blocking": criterion.blocking,
                "detail": detail,
            }

        should_downgrade, conf_adj = await self._check_learning_adjustment(criterion.learning_key)
        return self._build_failed_outcome(
            criterion,
            feedback=feedback_text,
            learning_adjusted=should_downgrade,
            confidence_adjustment=conf_adj,
            error=None,
            detail=detail,
        )

    def _unified_to_outcome(self, criterion: AuditCriterion, raw: Any) -> dict[str, Any]:
        """UnifiedAuditor の結果（degraded tuple / UnifiedAuditReport）を outcome 化。"""
        blocking = is_unified_auditor_blocking()

        if isinstance(raw, tuple):
            _state, reason = raw
            return self._build_failed_outcome(
                criterion,
                feedback=reason,
                learning_adjusted=False,
                confidence_adjustment=0.0,
                error=reason,
                detail={"degraded": True},
                blocking=False,
            )

        acceptable = bool(getattr(raw, "is_acceptable", False))
        final_score = float(getattr(raw, "final_score", 0.0))
        qualitative = getattr(raw, "qualitative", None)
        critique = str(getattr(qualitative, "critique", "") or "")
        conflicts = list(getattr(raw, "conflicts", []) or [])

        if acceptable:
            return {
                "audit_id": criterion.audit_id,
                "label": criterion.label,
                "passed": True,
                "feedback": critique,
                "severity": criterion.severity,
                "learning_adjusted": False,
                "confidence_adjustment": 0.0,
                "effective_severity": None,
                "error": None,
                "score": AUDIT_GATE_PASS_SCORE,
                "weight": 1.0,
                "blocking": False,
                "detail": {
                    "final_score": final_score,
                    "conflicts": [self._conflict_to_dict(c) for c in conflicts],
                },
            }

        return self._build_failed_outcome(
            criterion,
            feedback=critique or f"UnifiedAuditor が不合格と判定（score={final_score}）",
            learning_adjusted=False,
            confidence_adjustment=0.0,
            error=None,
            detail={
                "final_score": final_score,
                "conflicts": [self._conflict_to_dict(c) for c in conflicts],
            },
            blocking=blocking,
        )

    @staticmethod
    def _conflict_to_dict(conflict: Any) -> dict[str, Any]:
        if hasattr(conflict, "model_dump"):
            return dict(conflict.model_dump())
        if hasattr(conflict, "to_dict"):
            return dict(conflict.to_dict())
        return {"value": str(conflict)}

    def _build_failed_outcome(
        self,
        criterion: AuditCriterion,
        feedback: str,
        learning_adjusted: bool,
        confidence_adjustment: float,
        error: str | None,
        detail: dict[str, Any] | None = None,
        blocking: bool | None = None,
    ) -> dict[str, Any]:
        """不合格 outcome を severity 重み・学習調整込みで組み立てる。"""
        severity = "critical" if error else criterion.severity
        effective_severity = severity
        if learning_adjusted:
            effective_severity = AUDIT_GATE_DOWNGRADE.get(severity, severity)

        score = AUDIT_GATE_PENALTY_SCORE.get(effective_severity, 0.0)
        score += AUDIT_GATE_CONFIDENCE_WEIGHT * max(-1.0, min(1.0, confidence_adjustment))
        score = max(0.0, min(100.0, score))
        weight = AUDIT_GATE_SEVERITY_WEIGHTS.get(effective_severity, 1.0)

        return {
            "audit_id": criterion.audit_id,
            "label": criterion.label,
            "passed": False,
            "feedback": feedback,
            "severity": criterion.severity,
            "learning_adjusted": learning_adjusted,
            "confidence_adjustment": confidence_adjustment,
            "effective_severity": effective_severity,
            "error": error,
            "score": round(score, 2),
            "weight": weight,
            "blocking": criterion.blocking if blocking is None else blocking,
            "detail": detail or {},
        }

    # ------------------------------------------------------------------
    # 監査フェーズ実行（Step 21）
    # ------------------------------------------------------------------

    async def run_audit_phase(
        self,
        writing_context: dict[str, Any],
        drafted_text: str,
        book_id: int,
        ep_num: int,
        parallel: bool = True,
        branch_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], float]:
        """監査フェーズを実行し ``(outcomes, レイテンシ秒)`` を返す。

        Args:
            parallel: True なら ``asyncio.gather(return_exceptions=True)``、
                False なら直列（Step 22 の等価性検証用）。
        """
        started = time.perf_counter()

        plan = await self._run_core_audits(
            writing_context, drafted_text, book_id, ep_num, branch_id=branch_id
        )
        durations: dict[str, float] = {}

        def _timed(criterion: AuditCriterion, factory: Any) -> Any:
            async def _runner() -> Any:
                started_at = time.perf_counter()
                try:
                    return await factory()
                finally:
                    durations[criterion.audit_id] = time.perf_counter() - started_at

            return _runner

        for criterion, _factory in plan:
            self.emit_event(
                "audit.audit.started",
                {"book_id": book_id, "ep_num": ep_num, "audit_id": criterion.audit_id},
            )

        gathered: list[Any] = []
        if parallel:
            gathered = await asyncio.gather(
                *(_timed(criterion, factory)() for criterion, factory in plan),
                return_exceptions=True,
            )
        else:
            for criterion, factory in plan:
                try:
                    gathered.append(await _timed(criterion, factory)())
                except Exception as exc:  # 直列実行でも他判定を止めない
                    gathered.append(exc)

        outcomes: list[dict[str, Any]] = []
        for (criterion, _factory), raw in zip(plan, gathered, strict=True):
            if isinstance(raw, BaseException):
                outcome = self._build_failed_outcome(
                    criterion,
                    feedback=f"監査器が例外を送出: {type(raw).__name__}: {raw}",
                    learning_adjusted=False,
                    confidence_adjustment=0.0,
                    error=f"auditor_exception:{type(raw).__name__}",
                    detail={"exception": repr(raw)},
                )
            else:
                outcome = await self._to_outcome(criterion, raw)
            outcomes.append(outcome)

        # 定性的判断（UnifiedAuditor, v6-A2）は 5監査の入力を再利用するため直列で足す
        unified_criterion, unified_raw = await self._run_unified_auditor(
            writing_context, drafted_text
        )
        unified_started = time.perf_counter()
        self.emit_event(
            "audit.audit.started",
            {
                "book_id": book_id,
                "ep_num": ep_num,
                "audit_id": unified_criterion.audit_id,
            },
        )
        unified_outcome = await self._to_outcome(unified_criterion, unified_raw)
        durations[unified_criterion.audit_id] = time.perf_counter() - unified_started
        outcomes.append(unified_outcome)

        for outcome in outcomes:
            self.emit_event(
                "audit.audit.completed",
                {
                    "book_id": book_id,
                    "ep_num": ep_num,
                    "audit_id": outcome["audit_id"],
                    "passed": outcome["passed"],
                    "severity": outcome["severity"],
                    "effective_severity": outcome["effective_severity"],
                    "score": outcome["score"],
                    "error": outcome["error"],
                },
            )

        elapsed = time.perf_counter() - started
        self.last_audit_latency_seconds = elapsed
        self.last_audit_durations = durations
        self.emit_event(
            "audit.audit.phase_completed",
            {
                "book_id": book_id,
                "ep_num": ep_num,
                "parallel": parallel,
                "latency_seconds": round(elapsed, 6),
                "audit_ids": [o["audit_id"] for o in outcomes],
            },
        )
        return outcomes, elapsed

    # ------------------------------------------------------------------
    # ゲート判定（Step 23）
    # ------------------------------------------------------------------

    def evaluate_gate(self, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        """5監査を 0-100 に正規化し、severity 重み＋学習調整で集約する。

        戻り値は :func:`evaluate_gate` と同じ。最近の結果は
        ``last_gate_evaluation`` にも保持する。
        """
        evaluation = evaluate_gate(outcomes)
        self.last_gate_evaluation = evaluation
        return evaluation

    # ------------------------------------------------------------------
    # 局所パッチ（Step 25）
    # ------------------------------------------------------------------

    def _build_safe_replacer_mappings(self, report: Any) -> dict[str, str]:
        """UnifiedAuditor の指摘から SafeReplacer 用の置換表を作る。"""
        mappings: dict[str, str] = {}
        for conflict in getattr(report, "conflicts", []) or []:
            current = str(getattr(conflict, "current_value", "") or "")
            suggested = str(getattr(conflict, "suggested_value", "") or "")
            if current and suggested and current != suggested and len(current) <= 200:
                mappings[current] = suggested
        return mappings

    async def _try_span_patch(
        self,
        drafted_text: str,
        plan: Any,
    ) -> dict[str, Any] | None:
        """W4 Step 8: 段落単位のスパン置換（``RepairPlan.level == "span"`` のときだけ）。

        ``LocalPolisher.polish_span`` が検証付きで採用した (``ok=True``) ときだけ
        ``None`` 以外を返す。検証落ち・例外は ``None`` を返し、呼び出し側は
        既存経路（``actionable_patch`` / ``LocalPolisher``）へフォールバックする。
        """
        from src.generation.local_polish import LocalPolisher
        from src.services.prose.paragraph_indexer import ParagraphIndexer

        if getattr(plan, "level", "") != "span":
            return None
        targets = tuple(getattr(plan, "targets", ()) or ())
        if not targets:
            return None

        paragraphs = ParagraphIndexer().index_paragraphs(drafted_text)
        by_index = {p["index"]: p for p in paragraphs if p.get("start", -1) >= 0}
        target_index = int(targets[0])
        span = by_index.get(target_index)
        if span is None or span.get("end", -1) <= span.get("start", -1):
            return None

        patched, ok = await LocalPolisher().polish_span(
            drafted_text,
            (span["start"], span["end"]),
            "監査で指摘された箇所を本文のトーンと文脈に合わせて書き直してください。",
            self._audit_llm,
        )
        if not ok or not patched or patched == drafted_text:
            return None
        return {
            "strategy": "span_polish",
            "text": patched,
            "replacements": 1,
            "paragraph_index": target_index,
            "triage_level": plan.level,
        }

    async def try_local_patch(
        self,
        drafted_text: str,
        unified_report: Any = None,
        failed_outcomes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """全文再執筆の前に局所パッチを試みる（v5.0 1パッチPDCA と整合）。

        試行順（軽い・確度の高い順）:

        1. ``SafeReplacer`` — 決定的な 1パス置換（LLM 不要）
        2. ``span_polish`` — 段落単位のスパン置換（W4 Step 8, 検証付き LLM）
        3. ``actionable_patch`` — UnifiedAuditor の提示パッチ（LLM 不要）
        4. ``LocalPolisher`` — 対象範囲の再生成（LLM 使用）

        いずれも適用できないときのみ ``None`` を返し、呼び出し側は
        全文再執筆へフォールバックする。
        """
        if not drafted_text:
            self.emit_event("audit.patch.skipped", {"reason": "empty_drafted_text"})
            return None
        if not is_local_patch_enabled():
            self.emit_event("audit.patch.skipped", {"reason": "local_patch_disabled"})
            return None

        mappings = self._build_safe_replacer_mappings(unified_report)
        # W4 Step 8: 三段階トリアージの判定（純関数・LLM 呼び出しなし）
        plan = plan_repair(
            drafted_text, failed_outcomes or [], StaticRuleAuditor().audit(drafted_text)
        )
        plan_level = str(getattr(plan, "level", "") or "rule")
        span_rejected = False
        if mappings:
            try:
                from src.services.safe_replace import SafeReplacer

                patched = SafeReplacer(mappings).replace(drafted_text)
                if patched and patched != drafted_text:
                    self._repair_budget.record_local_patch()
                    self.emit_event(
                        "audit.patch.applied",
                        {
                            "strategy": "safe_replace",
                            "replacements": len(mappings),
                            "text_length": len(patched),
                            "triage_level": plan_level,
                        },
                    )
                    return {
                        "strategy": "safe_replace",
                        "text": patched,
                        "replacements": len(mappings),
                    }
            except Exception:
                logger.warning("SafeReplacer による局所パッチに失敗しました", exc_info=True)

        # W4 Step 8: 三段階トリアージのうち「span」段階を既存2段の間に挿す。
        if is_span_patch_enabled() and is_async_polish_enabled() and self._audit_llm is not None:
            try:
                span_result = await self._try_span_patch(drafted_text, plan)
            except Exception:
                logger.warning("span パッチに失敗しました", exc_info=True)
                span_result = None
                span_rejected = True
            if span_result is not None:
                self._repair_budget.record_local_patch()
                self.emit_event(
                    "audit.patch.applied",
                    {
                        "strategy": span_result["strategy"],
                        "replacements": span_result["replacements"],
                        "text_length": len(span_result["text"]),
                        "triage_level": span_result.get("triage_level", "span"),
                    },
                )
                return span_result
            span_rejected = True

        qualitative = getattr(unified_report, "qualitative", None)
        actionable = str(getattr(qualitative, "actionable_patch", "") or "").strip()
        if actionable:
            # writing_langgraph.py:615 と同じ「1パッチPDCA」方針
            self._repair_budget.record_local_patch()
            self.emit_event(
                "audit.patch.applied",
                {
                    "strategy": "actionable_patch",
                    "replacements": 1,
                    "text_length": len(drafted_text) + 2 + len(actionable),
                    "triage_level": plan_level,
                },
            )
            return {
                "strategy": "actionable_patch",
                "text": drafted_text + "\n\n" + actionable,
                "replacements": 1,
            }

        if self._audit_llm is None:
            self.emit_event("audit.patch.skipped", {"reason": "no_audit_llm"})
            return None
        quote = self._find_patchable_quote(drafted_text, unified_report)
        if not quote:
            self.emit_event("audit.patch.skipped", {"reason": "no_patchable_quote"})
            return None
        try:
            from src.generation.local_polish import LocalPolisher

            start = drafted_text.find(quote)
            polisher = LocalPolisher()
            # T6 Step 7: 注入された（計測可能な）LLM を渡す。
            # 旧実装はモジュールグローバル `call_llm_api` を直接呼ぶため
            # `tracked_adapter` をバイパスし、この経路の LLM コストが
            # 計測に一切乗っていなかった。
            improved = await polisher.polish_with_llm(
                drafted_text,
                (start, start + len(quote)),
                "監査で指摘された箇所を本文のトーンと文脈に合わせて書き直してください。",
                self._audit_llm,
            )
            if improved and improved != drafted_text:
                self._repair_budget.record_local_patch()
                self.emit_event(
                    "audit.patch.applied",
                    {
                        "strategy": "local_polish",
                        "replacements": 1,
                        "text_length": len(improved),
                        "triage_level": plan_level,
                    },
                )
                return {
                    "strategy": "local_polish",
                    "text": improved,
                    "replacements": 1,
                }
        except Exception:
            logger.warning("LocalPolisher による局所パッチに失敗しました", exc_info=True)
            self.emit_event("audit.patch.skipped", {"reason": "local_polish_exception"})
            return None
        self.emit_event(
            "audit.patch.skipped",
            {"reason": "span_patch_rejected" if span_rejected else "no_change"},
        )
        return None

    @staticmethod
    def _find_patchable_quote(drafted_text: str, unified_report: Any) -> str:
        """UnifiedAuditor の指摘のうち本文に実在する引用を 1 件返す。"""
        for conflict in getattr(unified_report, "conflicts", []) or []:
            candidate = str(getattr(conflict, "current_value", "") or "").strip()
            if not candidate or len(candidate) > 200:
                continue
            if candidate in drafted_text:
                return candidate
        return ""

    # ------------------------------------------------------------------
    # PatchReview
    # ------------------------------------------------------------------

    async def _create_patch_review(
        self,
        book_id: int,
        ep_num: int,
        patch_type: str,
        original_content: str,
        proposed_content: str,
        audit_issues: list[dict],
        learning_metadata: dict | None = None,
    ) -> int:
        """PatchReview レコードを作成し、IDを返す"""
        if self.repo is None:
            return 0

        # diff_json を生成（簡易版）
        diff_json = {
            "type": "audit_failure",
            "issues": audit_issues,
        }

        return await self.repo.misc.create_patch_review(
            book_id=book_id,
            ep_num=ep_num,
            patch_type=patch_type,
            original_content=original_content,
            proposed_content=proposed_content,
            diff_json=diff_json,
            audit_issue_ids=[
                issue.get("issue_id", 0) for issue in audit_issues if issue.get("issue_id")
            ],
            learning_metadata=learning_metadata,
        )

    async def _persist_failures(
        self,
        book_id: int,
        ep_num: int,
        drafted_text: str,
        failed_audits: list[dict[str, Any]],
        learning_adjusted_audits: list[str],
        patch_type: str = "audit_failure",
        proposed_content: str = "",
    ) -> int:
        """既存 AuditIssue と PatchReview を作成して PatchReview ID を返す。"""
        issue_ids: list[int] = []
        if self.repo:
            for audit in failed_audits:
                # 学習調整された場合は severity を下げる
                severity = audit["severity"]
                if audit.get("learning_adjusted"):
                    severity = "medium" if severity == "high" else "low"

                issue_id = await self.repo.audit.create_audit_issue(
                    book_id=book_id,
                    ep_num=ep_num,
                    category=audit["type"],
                    severity=severity,
                    description=audit["feedback"],
                )
                issue_ids.append(issue_id)

        return await self._create_patch_review(
            book_id=book_id,
            ep_num=ep_num,
            patch_type=patch_type,
            original_content=drafted_text,
            proposed_content=proposed_content,
            audit_issues=[
                {"type": a["type"], "feedback": a["feedback"], "issue_id": iid}
                for a, iid in zip(failed_audits, issue_ids)
            ],
            learning_metadata={
                "negative_sample_candidates": [a["type"] for a in failed_audits],
                "learning_adjusted": learning_adjusted_audits,
            },
        )

    @staticmethod
    def _to_legacy_failure(outcome: dict[str, Any]) -> dict[str, Any]:
        """outcome を既存 consumer 互換の failed_audits 要素へ変換する。"""
        return {
            "type": outcome["audit_id"],
            "feedback": outcome["feedback"],
            "severity": outcome["severity"],
            "learning_adjusted": outcome["learning_adjusted"],
            "confidence_adjustment": outcome["confidence_adjustment"],
            "audit_id": outcome["audit_id"],
            "effective_severity": outcome["effective_severity"],
            "score": outcome["score"],
            "error": outcome["error"],
        }

    # ------------------------------------------------------------------
    # エントリーポイント
    # ------------------------------------------------------------------

    async def execute(self, ctx: AgentContext) -> AgentResult:
        """スキル実行エントリーポイント。"""
        self.emit_event("audit.started", {
            "book_id": ctx.book_id,
            "ep_num": ctx.ep_num,
        })

        writing_context = ctx.artifacts.get("writing_context")
        # エンリッチメント済みテキストを優先、なければ元のドラフトを使用
        enriched_text = ctx.artifacts.get("enriched_text")
        drafted_text = enriched_text or ctx.artifacts.get("drafted_text")

        if not writing_context or not drafted_text:
            self.emit_event("audit.error", {
                "book_id": ctx.book_id,
                "ep_num": ctx.ep_num,
                "error": "writing_context and drafted_text are required in artifacts",
            })
            return AgentResult(
                next_agent=None,
                artifacts={},
                error="writing_context and drafted_text are required in artifacts",
            )

        book_id = ctx.book_id
        ep_num = ctx.ep_num

        try:
            # Step 21: 5監査を並列実行（判定は与传统同一。1件の例外は他を止めない）
            outcomes, latency = await self.run_audit_phase(
                writing_context, drafted_text, book_id, ep_num, parallel=True
            )

            failed_outcomes = [o for o in outcomes if not o["passed"] and o["blocking"]]
            failed_audits = [self._to_legacy_failure(o) for o in failed_outcomes]
            # 非ブロッキング（UnifiedAuditor の追加観測）は PatchReview を汚さないよう分離する
            advisories = [
                self._to_legacy_failure(o)
                for o in outcomes
                if not o["passed"] and not o["blocking"]
            ]
            learning_adjusted_audits = [
                o["audit_id"] for o in outcomes if o["learning_adjusted"]
            ]

            if learning_adjusted_audits:
                logger.info(
                    f"Learning-adjusted audits for Ep.{ep_num}: {learning_adjusted_audits}"
                )

            audit_metrics = {
                "latency_seconds": round(latency, 6),
                "audit_durations": {k: round(v, 6) for k, v in self.last_audit_durations.items()},
                "audit_ids": [o["audit_id"] for o in outcomes],
                "scores": {o["audit_id"]: o["score"] for o in outcomes},
            }

            # Step 23: スコア集約式ゲート（全滅式は ENABLE_AUDIT_SCORE_GATE=false で復元）
            gate = self.evaluate_gate(outcomes)
            # W4 Step 11: ゲート観測点に既存 audit_metrics を載せる（新規変数は作らない）
            if self.last_gate_evaluation is not None:
                self.last_gate_evaluation["audit_metrics"] = audit_metrics
            unified_report = self.last_unified_report

            # 全監査合格
            if not failed_audits:
                self.emit_event("audit.completed", {
                    "book_id": book_id,
                    "ep_num": ep_num,
                    "result": "passed",
                    "audit_ids": audit_metrics["audit_ids"],
                    "latency_seconds": audit_metrics["latency_seconds"],
                })
                return AgentResult(
                    next_agent=AgentName.ILLUSTRATION,
                    should_retry=False,
                    is_backtrack=False,
                    artifacts={
                        "audit_report": {
                            "logical": "passed",
                            "deai": "passed",
                            "ability": "passed",
                            "causal": "passed",
                        },
                        "audit_status": "passed",
                        "audit_advisories": advisories,
                        "audit_metrics": audit_metrics,
                        "gate_evaluation": gate,
                    },
                )

            # Step 25: 全文再執筆の前に局所パッチを優先（1パッチPDCA）
            # W4 Step 8: どの是正手段を使うか判断するため failed outcome を渡す。
            # `outcomes` は run_audit_phase の戻り値なので、そのまま outcome 相当。
            patch_result = (
                await self.try_local_patch(drafted_text, unified_report, failed_outcomes)
                if gate["requires_regeneration"]
                else None
            )

            if patch_result is not None:
                patch_review_id = await self._persist_failures(
                    book_id=book_id,
                    ep_num=ep_num,
                    drafted_text=drafted_text,
                    failed_audits=failed_audits,
                    learning_adjusted_audits=learning_adjusted_audits,
                    patch_type="local_patch",
                    proposed_content=patch_result["text"],
                )
                self.emit_event("audit.completed", {
                    "book_id": book_id,
                    "ep_num": ep_num,
                    "result": "patched",
                    "patch_strategy": patch_result["strategy"],
                    "aggregate_score": gate["aggregate_score"],
                })
                return AgentResult(
                    next_agent=AgentName.ILLUSTRATION,
                    should_retry=False,
                    is_backtrack=False,
                    error=None,
                    artifacts={
                        "audit_feedback": "Audit issues resolved by local patch",
                        "requires_user_review": True,
                        "patch_review_id": patch_review_id,
                        "patched_text": patch_result["text"],
                        "patch_strategy": patch_result["strategy"],
                        "failed_audits": failed_audits,
                        "audit_advisories": advisories,
                        "learning_adjusted_audits": learning_adjusted_audits,
                        "audit_status": "patched",
                        "audit_metrics": audit_metrics,
                        "gate_evaluation": gate,
                    },
                )

            patch_review_id = await self._persist_failures(
                book_id=book_id,
                ep_num=ep_num,
                drafted_text=drafted_text,
                failed_audits=failed_audits,
                learning_adjusted_audits=learning_adjusted_audits,
            )

            if not gate["requires_regeneration"]:
                # 軽微な失敗は続行する（ユーザー確認と PatchReview は残す）
                self.emit_event("audit.completed", {
                    "book_id": book_id,
                    "ep_num": ep_num,
                    "result": "passed_with_warnings",
                    "aggregate_score": gate["aggregate_score"],
                })
                return AgentResult(
                    next_agent=AgentName.ILLUSTRATION,
                    should_retry=False,
                    is_backtrack=False,
                    error=None,
                    artifacts={
                        "audit_feedback": "Audit completed with minor issues",
                        "requires_user_review": True,
                        "patch_review_id": patch_review_id,
                        "failed_audits": failed_audits,
                        "audit_advisories": advisories,
                        "learning_adjusted_audits": learning_adjusted_audits,
                        "audit_status": "passed_with_warnings",
                        "audit_metrics": audit_metrics,
                        "gate_evaluation": gate,
                    },
                )

            # W4 Step 10: 予算切れなら「パッチ出来なかった → 警告通過」側に落とす。
            # Orchestrator の max_backtracks_per_node=3 だと1話あたり最大4回
            # 全文書きする。1話1回に封じ込める。
            if is_repair_budget_enabled() and not self._repair_budget.should_regenerate_full_text():
                self.emit_event("audit.completed", {
                    "book_id": book_id,
                    "ep_num": ep_num,
                    "result": "repassed_budget_exhausted",
                    "aggregate_score": gate["aggregate_score"],
                })
                return AgentResult(
                    next_agent=AgentName.ILLUSTRATION,
                    should_retry=False,
                    is_backtrack=False,
                    error=None,
                    artifacts={
                        "audit_feedback": (
                            "Audit failed but full regeneration budget is exhausted"
                        ),
                        "requires_user_review": True,
                        "patch_review_id": patch_review_id,
                        "failed_audits": failed_audits,
                        "audit_advisories": advisories,
                        "learning_adjusted_audits": learning_adjusted_audits,
                        "audit_status": "repassed_budget_exhausted",
                        "audit_metrics": audit_metrics,
                        "gate_evaluation": gate,
                    },
                )

            # Orchestratorのバックトラックメカニズムと統一するため、should_retry=Trueに設定
            # 次のエージェントはWRITING（再執筆）とし、is_backtrackフラグを設定
            feedback_list = [audit["feedback"] for audit in failed_audits if audit.get("feedback")]
            regeneration_directive = ""
            if feedback_list:
                sugg_text = "、".join(feedback_list[:3])  # 上位3件のフィードバックを使用
                regeneration_directive = (
                    f"【再生成指示 - 品質改善項目】\nスコア向上のため以下を反映して書き直してください: {sugg_text}"
                )

            # W4 Step 10/11: Branch D を通った分だけ予算を消費し、観測イベントを出す。
            self._repair_budget.record_full_regeneration()
            self.emit_event(
                "audit.regeneration.full",
                {"attempt": self._repair_budget.regeneration_count},
            )

            self.emit_event("audit.completed", {
                "book_id": book_id,
                "ep_num": ep_num,
                "result": "rejected",
                "aggregate_score": gate["aggregate_score"],
            })
            return AgentResult(
                next_agent=AgentName.WRITING,
                should_retry=True,
                is_backtrack=True,
                error=None,
                artifacts={
                    "audit_feedback": "Audit failed - retrying writing",
                    "requires_user_review": True,
                    "patch_review_id": patch_review_id,
                    "failed_audits": failed_audits,
                        "audit_advisories": advisories,
                    "learning_adjusted_audits": learning_adjusted_audits,
                    "audit_status": "rejected",
                    "regeneration_directive": regeneration_directive,
                    "audit_metrics": audit_metrics,
                    "gate_evaluation": gate,
                },
            )

        except Exception as e:
            self.emit_event("audit.error", {
                "book_id": ctx.book_id,
                "ep_num": ctx.ep_num,
                "error": str(e),
            })
            return AgentResult(
                next_agent=None,
                artifacts={},
                error=f"Audit failed with exception: {e}",
            )

    async def run_specialist_audit(
        self,
        ctx: AgentContext,
        genre: str = "general",
        phase: str = "first_three_chapters",
    ) -> dict[str, Any]:
        """8専門家オーディター（AuditAggregator）を実行・集約するアダプタメソッド (Phase 6: Step 66)."""
        try:
            from src.services.audit_aggregator import AuditAggregator
            from src.services.genre_audit_weights import get_genre_weights

            weights = get_genre_weights(genre, phase)
            aggregator = AuditAggregator.from_default_registry(weights=weights)
            await aggregator.run_all(ctx)
            result = aggregator.aggregate()
            return result.to_dict()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Specialist audit failed, fallback to empty: {e}")
            return {
                "overall": 0.0,
                "by_specialist": {},
                "missing": [],
                "error": str(e),
            }

    async def run(self, ctx: AgentContext) -> AgentResult:
        """Orchestrator 用エントリーポイント。execute をラップする。"""
        return await self.execute(ctx)


# Step 68: スキル駆動パイプライン用のエイリアス
AuditSkillAgent = AuditAgent
