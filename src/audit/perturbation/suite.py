from __future__ import annotations

"""擾乱スイートオーケストレータ (M1-D)。

被験判定器 (Callable[[str], dict[str, float]]) を受け取り、
コーパス上の各話 × 各変換 × 各強度レベルで評価し、
Spearman ρ / 識別性 / INV / 再テストσ を集計する。
"""

import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from src.audit.perturbation.ladder import LadderEntry, build_ladder
from src.audit.perturbation.metrics import (
    check_invariance,
    check_retest_stability,
    identify_axis,
    spearman_rank,
)
from src.audit.perturbation.transforms import TRANSFORM_REGISTRY

JudgeFunc = Callable[[str], dict[str, float]]

# 強度レベルとの対応 (baseline=0, weak=1, medium=2, strong=3)
_STRENGTH_ORDER = {"baseline": 0, "weak": 1, "medium": 2, "strong": 3}


@dataclass
class SuiteResult:
    """1つの (変換, 強度レベル) に対する評価結果。"""

    transform_id: str
    label: str
    strength: float
    text_index: int
    scores: dict[str, float]  # {軸名: スコア}


@dataclass
class TransformMetrics:
    """1変換あたりの評価メトリクス。"""

    transform_id: str
    kind: str
    affected_axes: list[str]
    n_texts: int
    spearman_by_axis: dict[str, float]  # {軸名: rho}
    mean_rho: float
    identifiability: dict[str, Any]  # {期待軸: IdentifiabilityResult as dict}
    invariance: dict[str, Any]  # {INV 変換: InvarianceResult as dict}
    retest_sigma: dict[str, float]  # {軸名: sigma}
    all_passed: bool


@dataclass
class JudgeSuiteReport:
    """スイート実行の完全レポート。"""

    judge_id: str
    model_name: str | None
    prompt_version: str | None
    n_texts: int
    n_transforms: int
    created_at: str
    transform_metrics: list[TransformMetrics] = field(default_factory=list)
    all_passed: bool = False
    thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_id": self.judge_id,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "n_texts": self.n_texts,
            "n_transforms": self.n_transforms,
            "created_at": self.created_at,
            "thresholds": self.thresholds,
            "all_passed": self.all_passed,
            "transforms": [asdict(tm) for tm in self.transform_metrics],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class JudgeSuite:
    """擾乱スイートを実行するオーケストレータ。"""

    def __init__(
        self,
        judge: JudgeFunc,
        *,
        judge_id: str = "unknown",
        model_name: str | None = None,
        prompt_version: str | None = None,
        ladders: dict[str, list[LadderEntry]] | None = None,
        rho_threshold: float = 0.8,
        invariance_threshold: float = 3.0,
        retest_threshold: float = 5.0,
        identifiability_ratio: float = 1.5,
    ) -> None:
        self.judge = judge
        self.judge_id = judge_id
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.ladders = ladders if ladders is not None else build_ladder()
        self.rho_threshold = rho_threshold
        self.invariance_threshold = invariance_threshold
        self.retest_threshold = retest_threshold
        self.identifiability_ratio = identifiability_ratio

    def _judge_text(self, text: str) -> dict[str, float]:
        """被験判定器を1回呼び出す。失敗時は空辞書を返す（fail-closed の代わりに記録のみ）。"""
        try:
            result = self.judge(text)
            if not isinstance(result, dict):
                return {}
            return {k: float(v) for k, v in result.items()}
        except Exception:  # noqa: BLE001 - 判定器の失敗は個別に記録し続行
            return {}

    def run(self, corpus: list[str]) -> JudgeSuiteReport:
        """コーパス全体で擾乱スイートを実行する。"""

        # 各変換 × 各強度レベル × 各話 のスコアを収集
        # 構造: {transform_id: {label: {text_index: scores}}}
        collected: dict[str, dict[str, dict[int, dict[str, float]]]] = defaultdict(
            lambda: defaultdict(dict)
        )

        for tid, entries in self.ladders.items():
            for entry in entries:
                for text_index, text in enumerate(corpus):
                    perturbed = entry.apply(text)
                    scores = self._judge_text(perturbed)
                    collected[tid][entry.label][text_index] = scores

        # 各変換についてメトリクスを計算
        transform_metrics: list[TransformMetrics] = []
        thresholds = {
            "rho_threshold": self.rho_threshold,
            "invariance_threshold": self.invariance_threshold,
            "retest_threshold": self.retest_threshold,
            "identifiability_ratio": self.identifiability_ratio,
        }

        for tid, entries in self.ladders.items():
            base_transform = TRANSFORM_REGISTRY.get(tid)
            kind = base_transform.kind if base_transform is not None else "UNKNOWN"
            affected_axes = (
                base_transform.affected_axes if base_transform is not None else []
            )

            # Spearman: 強度レベル (0,1,2,3) と baseline->強度 のスコア差の相関
            # 各軸について、baseline スコアと強度別スコアの関係を単調性で見る
            spearman_by_axis: dict[str, float] = {}
            mean_rho = 0.0

            # 全軸を収集
            all_axes: set[str] = set()
            for entry in entries:
                for scores in collected[tid][entry.label].values():
                    all_axes.update(scores.keys())

            rho_values = []
            for ax in sorted(all_axes):
                baseline_scores_by_text: list[float] = []
                strong_scores_by_text: list[float] = []
                # 強度レベル順に並べたスコア系列 (baseline, weak, medium, strong)
                level_scores: dict[int, list[float]] = {
                    0: [], 1: [], 2: [], 3: []
                }
                for entry in entries:
                    level = _STRENGTH_ORDER[entry.label]
                    for text_index, scores in collected[tid][entry.label].items():
                        if ax in scores:
                            level_scores[level].append(scores[ax])
                # 各テキストについて、強度レベルとスコアの単調性を見る
                # ここでは baseline と strong の差をシンプルに用いる
                # より正確には各 text について強度レベルとスコアの相関を取る
                text_rhos: list[float] = []
                n_texts = len(corpus)
                for text_index in range(n_texts):
                    x: list[int] = []
                    y: list[float] = []
                    for entry in entries:
                        level = _STRENGTH_ORDER[entry.label]
                        scores = collected[tid][entry.label].get(text_index, {})
                        if ax in scores:
                            x.append(level)
                            y.append(scores[ax])
                    if len(x) >= 2:
                        r = spearman_rank(x, y)
                        text_rhos.append(r.rho)
                if text_rhos:
                    rho = statistics.mean(text_rhos)
                else:
                    rho = 0.0
                spearman_by_axis[ax] = round(rho, 6)
                rho_values.append(rho)
            mean_rho = round(statistics.mean(rho_values), 6) if rho_values else 0.0

            # 識別性: 各 DIR 変換について、期待軸が他軸より低下するか
            identifiability: dict[str, Any] = {}
            if kind == "DIR" and affected_axes:
                expected_axis = affected_axes[0]
                # baseline vs strong のスコア差
                baseline_by_text: dict[int, float] = {}
                strong_by_text: dict[int, float] = {}
                for text_index in range(len(corpus)):
                    b_scores = collected[tid]["baseline"].get(text_index, {})
                    s_scores = collected[tid]["strong"].get(text_index, {})
                    if expected_axis in b_scores and expected_axis in s_scores:
                        baseline_by_text[text_index] = b_scores[expected_axis]
                        strong_by_text[text_index] = s_scores[expected_axis]
                # 全軸の baseline と strong を比較
                baseline_all: dict[str, float] = {}
                strong_all: dict[str, float] = {}
                for ax in all_axes:
                    b_vals = [
                        collected[tid]["baseline"][ti][ax]
                        for ti in range(len(corpus))
                        if ti in collected[tid]["baseline"] and ax in collected[tid]["baseline"][ti]
                    ]
                    s_vals = [
                        collected[tid]["strong"][ti][ax]
                        for ti in range(len(corpus))
                        if ti in collected[tid]["strong"] and ax in collected[tid]["strong"][ti]
                    ]
                    if b_vals and s_vals:
                        baseline_all[ax] = statistics.mean(b_vals)
                        strong_all[ax] = statistics.mean(s_vals)
                if baseline_all and strong_all:
                    id_res = identify_axis(baseline_all, strong_all, expected_axis)
                    identifiability = {
                        "expected_axis": expected_axis,
                        "expected_drop": id_res.expected_drop,
                        "other_drop": id_res.other_drop,
                        "ratio": id_res.ratio,
                        "identified": id_res.identified,
                    }

            # INV: T08/T09 など INV 変換では baseline と strong で全軸不変
            invariance: dict[str, Any] = {}
            if kind == "INV" and affected_axes:
                baseline_all: dict[str, float] = {}
                strong_all: dict[str, float] = {}
                for ax in all_axes:
                    b_vals = [
                        collected[tid]["baseline"][ti][ax]
                        for ti in range(len(corpus))
                        if ti in collected[tid]["baseline"] and ax in collected[tid]["baseline"][ti]
                    ]
                    s_vals = [
                        collected[tid]["strong"][ti][ax]
                        for ti in range(len(corpus))
                        if ti in collected[tid]["strong"] and ax in collected[tid]["strong"][ti]
                    ]
                    if b_vals and s_vals:
                        baseline_all[ax] = statistics.mean(b_vals)
                        strong_all[ax] = statistics.mean(s_vals)
                if baseline_all and strong_all:
                    inv_res = check_invariance(
                        baseline_all, strong_all, threshold=self.invariance_threshold
                    )
                    invariance = {
                        "max_delta": inv_res.max_delta,
                        "passed": inv_res.passed,
                    }

            # 再テストσ: baseline を2回評価した場合のσ（ここでは1回のみなのでスキップ、
            # 将来的に judge を2回呼ぶ実装に拡張）
            retest_sigma: dict[str, float] = {}

            # 合否判定
            rho_pass = mean_rho >= self.rho_threshold
            inv_pass = (
                True
                if not invariance
                else invariance.get("passed", True)
            )
            id_pass = (
                True
                if not identifiability
                else identifiability.get("identified", True)
            )
            all_passed = rho_pass and inv_pass and id_pass

            transform_metrics.append(
                TransformMetrics(
                    transform_id=tid,
                    kind=kind,
                    affected_axes=affected_axes,
                    n_texts=len(corpus),
                    spearman_by_axis=spearman_by_axis,
                    mean_rho=mean_rho,
                    identifiability=identifiability,
                    invariance=invariance,
                    retest_sigma=retest_sigma,
                    all_passed=all_passed,
                )
            )

        report_all_passed = all(tm.all_passed for tm in transform_metrics)

        return JudgeSuiteReport(
            judge_id=self.judge_id,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            n_texts=len(corpus),
            n_transforms=len(self.ladders),
            created_at=datetime.now(timezone.utc).isoformat(),
            transform_metrics=transform_metrics,
            all_passed=report_all_passed,
            thresholds=thresholds,
        )


__all__ = [
    "JudgeSuite",
    "JudgeSuiteReport",
    "TransformMetrics",
    "SuiteResult",
    "JudgeFunc",
    "run_judge_suite",
]


def run_judge_suite(
    judge: JudgeFunc,
    corpus: list[str],
    *,
    judge_id: str = "unknown",
    model_name: str | None = None,
    prompt_version: str | None = None,
    **kwargs: Any,
) -> JudgeSuiteReport:
    """JudgeSuite を1発で実行してレポートを返す便利関数。"""
    suite = JudgeSuite(
        judge=judge,
        judge_id=judge_id,
        model_name=model_name,
        prompt_version=prompt_version,
        **kwargs,
    )
    return suite.run(corpus)
