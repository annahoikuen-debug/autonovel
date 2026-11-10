"""PLAN_S1 N2: 物語構造ゲート — narrative_balancer の本番配線層。

STORY_SPINE / narrative_balancer (DSP/CSP/Grammar) は実装済みだが本番パイプラインに
効いていなかった (PLAN_S1 G-1)。本モジュールは ``DefaultPlotExpander.expand_macro_skeletons``
で生成したマクロ骨子 (:class:`src.models.plot.EpisodeMacroSkeleton`, tension 0-100) を
narrative_balancer の :class:`src.narrative_balancer.models.Beat` (tension 0-10) に変換し、
CSP 物理則 (連続話間 |Δtension| ≤ max_step_delta / 3話ローリング合計 ≥ rolling_min_sum)
に照らして検査・補正する。

設計拘束 (PLAN_S1 §2):
- **P1 off で差分ゼロ**: mode=off (既定) では何もせず、呼び出しコストもゼロ。
- **P2 LLM 0 回・決定論**: balancer 経路に LLM は登場しない。CP-SAT は同入力→同出力。
- **P3 fail-open**: いかなる例外も執筆パイプラインを止めない (off 挙動へフォールバック)。
  監査 (fail-closed) とは逆方針であることに注意。
- **P4 SSOT**: 制約定数・mode は ``config/narrative_structure.yaml`` に置く。
  優先順位: 環境変数 NARRATIVE_STRUCTURE_GATE > yaml > コード内デフォルト
  (改善 #9 の calibration_store と同一パターン)。
- **P6 enforce は tension のみ**: beat_type / summary / characters 等の
  物語設計フィールドは上書き禁止 (yaml の enforce_overwrite_forbidden)。

使い方::

    gate = NarrativeStructureGate()
    report = gate.run(skeletons, reporter=reporter)
    if report.mode == "enforce":
        # skeletons の tension が補正済み (in-place)
"""

from __future__ import annotations

import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, Field

from src.narrative_balancer import Beat, BeatType, GlobalNarrativeBalancer, PlotState

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/narrative_structure.yaml"
VALID_MODES: Tuple[str, ...] = ("off", "warn", "enforce")
ENV_MODE_KEY = "NARRATIVE_STRUCTURE_GATE"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "version": 1,
    "mode": "off",
    "max_step_delta": 4.0,
    "rolling_min_sum": 6.0,
    "rolling_window": 3,
    "gate_timeout_seconds": 10.0,
    "enforce_overwrite_forbidden": [
        "beat_type",
        "summary",
        "characters",
        "is_defeat",
        "title",
        "foreshadowing_plan",
    ],
    "beat_type_mapping": {
        # normalize_chain_phase の出力語彙 (src/models/base.py)
        "Friction": "SETUP",
        "Prep": "RISING",
        "Discovery": "BATTLE",
        "Hate": "DISASTER",
        "Payoff": "PAYOFF",
        "Bonding": "RECOVERY",
        "Fulfillment": "RESOLUTION",
        # src/domain/entities/plot.py ChainPhase (Enum) の語彙 (後方互換)
        "Turn": "RISING",
        "CounterTurn": "BATTLE",
        "Resolution": "RESOLUTION",
        "Catharsis": "PAYOFF",
        "MicroCatharsis": "RECOVERY",
    },
    "default_tension": 5.0,
}

# tension 0-100 (マクロ骨子) と 0-10 (Beat) のスケール差
TENSION_SCALE = 10.0


class NarrativeStructureSettings(BaseModel):
    """``config/narrative_structure.yaml`` の SSOT スキーマ (N6)。"""

    version: int = 1
    mode: str = "off"
    max_step_delta: float = Field(default=4.0, ge=0.0, le=10.0)
    rolling_min_sum: float = Field(default=6.0, ge=0.0)
    rolling_window: int = Field(default=3, ge=2)
    gate_timeout_seconds: float = Field(default=10.0, ge=0.1)
    enforce_overwrite_forbidden: List[str] = Field(
        default_factory=lambda: list(DEFAULT_SETTINGS["enforce_overwrite_forbidden"])
    )
    beat_type_mapping: Dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SETTINGS["beat_type_mapping"])
    )
    default_tension: float = Field(default=5.0, ge=0.0, le=10.0)

    @property
    def max_step_delta_macro(self) -> float:
        """0-100 スケール換算の許容ステップ差 (N4 の micro 経路でも使用)。"""
        return self.max_step_delta * TENSION_SCALE

    @property
    def rolling_min_sum_macro(self) -> float:
        """0-100 スケール換算のローリング合計下限。"""
        return self.rolling_min_sum * TENSION_SCALE


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(config_path: Optional[str] = None) -> NarrativeStructureSettings:
    """SSOT 設定を読み込む。優先順位: env > yaml > コード内デフォルト。

    未知の mode は off に倒す (``get_spine_quality()`` のパターン踏襲)。
    yaml 欠落時もデフォルトで継続する (fail-open)。
    """
    path = config_path or os.getenv("AUTONOVEL_NARRATIVE_STRUCTURE_CONFIG") or DEFAULT_CONFIG_PATH
    data: Dict[str, Any] = {}
    try:
        yaml_path = Path(path)
        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001 - P3: 設定読み込み失敗でもデフォルトで継続
        logger.debug("narrative_structure.yaml load skipped: %s", exc)

    merged = _deep_merge(DEFAULT_SETTINGS, data)
    # YAML 1.1 は bare の off/on をブールにパースするため文字列へ正規化する
    raw_mode = merged.get("mode")
    if isinstance(raw_mode, bool) or not isinstance(raw_mode, str):
        merged["mode"] = "off"
    settings = NarrativeStructureSettings.model_validate(merged)

    env_mode = os.getenv(ENV_MODE_KEY, "").strip().lower()
    if env_mode:
        settings.mode = env_mode if env_mode in VALID_MODES else "off"
    if settings.mode not in VALID_MODES:
        settings.mode = "off"
    return settings


@lru_cache(maxsize=1)
def _cached_settings() -> NarrativeStructureSettings:
    return load_settings()


def get_settings() -> NarrativeStructureSettings:
    """現在の SSOT 設定を返す (プロセス内で 1 度だけファイルを読む)。"""
    return _cached_settings()


def get_gate_mode() -> str:
    """現在のゲートモードを返す (off / warn / enforce)。"""
    return _cached_settings().mode


def reset_settings_cache() -> None:
    """テスト用: SSOT キャッシュを無効化する (env 変更直後など)。"""
    _cached_settings.cache_clear()


def convert_tension(raw: Any, default: float = 5.0) -> Optional[float]:
    """0-100 スケールの生テンションを 0-10 スケールへ変換する (Q2 対象)。

    - None / NaN / 変換不能 → None (Beat.tension の Optional 契約)
    - 範囲外は 0-10 にクランプ (150 → 10.0, -5 → 0.0)
    """
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return max(0.0, min(10.0, value / TENSION_SCALE))


def _field(obj: Any, name: str, fallback: Any = None) -> Any:
    """属性アクセスと dict アクセスの両方に対応する取得ヘルパ。"""
    if isinstance(obj, dict):
        return obj.get(name, fallback)
    return getattr(obj, name, fallback)


def _as_phase_string(raw: Any) -> str:
    """ChainPhase (Enum) / 文字列を BeatType マッピング用の値へ正規化する。"""
    if raw is None:
        return "Friction"
    value = getattr(raw, "value", raw)
    return str(value)


def detect_tension_violations(
    beats: Sequence[Beat],
    settings: NarrativeStructureSettings,
) -> List[str]:
    """CSP 物理則 (SSOT 定数) に基づくテンション違反を検出する。

    検出対象は 2 制約のみ:
      1. 連続話間 |Δtension| ≤ max_step_delta
      2. rolling_window 話のローリング合計 ≥ rolling_min_sum
    テンション欠損 (None) の話は両制約の判定から除外する。

    これは balancer 内部の ``TensionPhysicsConstraintBuilder``
    (``src/narrative_balancer/csp/tension_constraints.py:22-29``) と同じ制約を
    SSOT 定数で検査する**ゲート契約**であり、ソルバーの再実装ではない (P5)。
    """
    violations: List[str] = []
    known: List[Tuple[int, float]] = [
        (b.episode, float(b.tension)) for b in beats if b.tension is not None
    ]

    for (ep_a, t_a), (ep_b, t_b) in zip(known, known[1:]):
        delta = abs(t_b - t_a)
        if delta > settings.max_step_delta:
            violations.append(
                f"tension jump between ep {ep_a} and ep {ep_b}: "
                f"|{t_a:.1f} -> {t_b:.1f}| = {delta:.1f} > max_step_delta {settings.max_step_delta:g}"
            )

    window = settings.rolling_window
    for start in range(len(known) - window + 1):
        chunk = known[start : start + window]
        total = sum(t for _, t in chunk)
        if total < settings.rolling_min_sum:
            episodes_desc = ", ".join(f"ep{ep}={t:.1f}" for ep, t in chunk)
            violations.append(
                f"rolling {window}-episode sum {total:.1f} < {settings.rolling_min_sum:g} "
                f"({episodes_desc})"
            )

    return violations


class BeatMapper:
    """:class:`EpisodeMacroSkeleton` (tension 0-100) → :class:`Beat` (tension 0-10) 変換。

    話数は**位置合わせのために 1..N に再採番**する (balancer の CorrectionApplier は
    1 始まり連番を前提とするため)。元骨子との対応はソート順の位置で保持され、
    :meth:`apply_tension_back` が同じソート順でテンションを書き戻す。
    """

    def __init__(self, settings: Optional[NarrativeStructureSettings] = None):
        self.settings = settings or load_settings()

    def to_beats(self, episodes: Sequence[Any]) -> List[Beat]:
        """骨子列を Beat 列へ変換する。ep_num で安定ソートし、1..N に再採番する。"""
        sorted_episodes = self.sort_episodes(episodes)
        mapping = self.settings.beat_type_mapping
        beats: List[Beat] = []
        for index, episode in enumerate(sorted_episodes, start=1):
            phase = _as_phase_string(_field(episode, "current_chain_phase", "Friction"))
            try:
                beat_type = BeatType(mapping.get(phase, "SETUP"))
            except ValueError:
                beat_type = BeatType.SETUP

            raw_tension = _field(episode, "tension", None)
            tension = convert_tension(raw_tension, self.settings.default_tension)

            foreshadowing = _field(episode, "foreshadowing_plan", []) or []
            beats.append(
                Beat(
                    episode=index,
                    tension=tension,
                    beat_type=beat_type,
                    title=str(_field(episode, "title", "") or ""),
                    summary=str(_field(episode, "one_line_summary", "") or ""),
                    characters=[],
                    is_defeat=False,
                    foreshadowing_setup=[str(item) for item in foreshadowing],
                    foreshadowing_payoff=[],
                )
            )
        return beats

    @staticmethod
    def sort_episodes(episodes: Sequence[Any]) -> List[Any]:
        """ep_num 昇順に安定ソートする (同話数は入力順を維持)。"""
        return sorted(
            episodes,
            key=lambda ep: (_field(ep, "ep_num", 0) if _field(ep, "ep_num", 0) is not None else 0),
        )

    def apply_tension_back(self, sorted_episodes: Sequence[Any], beats: Sequence[Beat]) -> int:
        """enforce 用: balancer 出力の tension (0-10) を骨子 (0-100 int) へ書き戻す。

        P6: 書き戻すフィールドは **tension のみ**。beat_type / summary 等には触れない。
        戻り値は値が変化した話数。
        """
        changed = 0
        for episode, beat in zip(sorted_episodes, beats):
            if beat.tension is None:
                continue
            new_value = int(round(max(0.0, min(10.0, float(beat.tension))) * TENSION_SCALE))
            try:
                old_value = int(_field(episode, "tension", 0) or 0)
            except (TypeError, ValueError):
                old_value = 0
            if new_value != old_value:
                try:
                    episode.tension = new_value  # type: ignore[attr-defined]
                    changed += 1
                except (AttributeError, TypeError):
                    # 不変オブジェクト等は書き戻しを諦める (fail-open)
                    continue
        return changed


def _scaled_csp_config(n_episodes: int) -> Any:
    """バッチ長にスケールした CSPConfig を構成する (N2)。

    CSP のデフォルト設定 (``config/csp_balancer.yaml``) は 40 話前提のため、
    それ未満のバッチでは midpoint/climax 制約が存在しない話数を指して
    実行不可能になる。ゲートはバッチ長 N に合わせて構造マイルストーンを
    内挿する (設定の派生であり、ソルバー実装の変更ではない / P5)。

    ``min_defeats=0``: ゲートは敗北イベントを新たに強制しない
    (P6: 物語設計フィールドへの介入禁止。tension のみを補正対象とする)。
    """
    from src.narrative_balancer.csp.config import CSPConfig

    n = max(4, int(n_episodes))
    from src.narrative_balancer.csp.config import CSPSolverSettings

    return CSPConfig(
        n_episodes=n,
        midpoint_episode=max(2, n // 2),
        midpoint_min_tension=7,
        all_is_lost_episode=max(1, (n * 3) // 4),
        all_is_lost_max_tension=4,
        climax_episode=n,
        climax_min_tension=8,
        min_defeats=0,
        max_defeats=n,
        max_payoff_distance=max(1, n // 2),
        # P2 (決定論): CP-SAT は複数ワーカーだと探索の絡みで非決定論的になるため 1 固定
        solver=CSPSolverSettings(max_time_seconds=5.0, num_search_workers=1),
    )


def build_batch_balancer(n_episodes: int) -> GlobalNarrativeBalancer:
    """バッチ長に合わせた GlobalNarrativeBalancer を構築する。

    - CSP アダプタにスケール済み config を注入 (上記 ``_scaled_csp_config``)
    - ``validate_output=False``: デフォルトの ``validate_full`` は 40 話前提のため
      非対応長のバッチで偽違反 ("Expected 40 episodes") を出す。
      ゲートは SSOT 定数による自前検出 (``detect_tension_violations``) を使うため、
      二重検証は無効化する。
    """
    from src.narrative_balancer.arbitrator.config import ArbitratorConfig
    from src.narrative_balancer.arbitrator.ports import CSPAdapter
    from src.narrative_balancer.csp.balancer import CSPNarrativeBalancer

    balancer = GlobalNarrativeBalancer(config=ArbitratorConfig(validate_output=False))
    balancer.adapters["csp"] = CSPAdapter(
        CSPNarrativeBalancer(config=_scaled_csp_config(n_episodes))
    )
    return balancer


class StructureGateReport(BaseModel):
    """ゲート実行結果。reporter への報告とテスト検証の両方に使う。"""

    model_config = {"extra": "ignore"}

    mode: str
    executed: bool = False
    violation_count: int = 0
    violations: List[str] = Field(default_factory=list)
    corrected_episode_count: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None
    curve_deviation: Optional[float] = None  # O3: 参照曲線からの平均逸脱 (0-100 スケール・advisory)


def compute_curve_deviation(
    beats: Sequence[Beat],
    tension_curve: Sequence[Sequence[float]],
) -> Optional[float]:
    """参照曲線 (進行度 0-1 × テンション 0-1) からの平均逸脱を返す (O3・advisory)。

    0-100 スケールの平均絶対偏差。曲線が不正 / 欠損話のみのとき None。
    判定ゲートではなく計測値であり、R1 の違反率実測と併用して解禁判断に使う。
    """
    known = [float(b.tension) * TENSION_SCALE for b in beats if b.tension is not None]
    points: List[Tuple[float, float]] = []
    for point in tension_curve or []:
        try:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), max(0.0, min(1.0, float(point[1])))))
        except (TypeError, ValueError):
            continue
    if not known or not points:
        return None
    points.sort(key=lambda p: p[0])
    n = len(known)
    deviations: List[float] = []
    for index in range(n):
        progress = (index + 1) / n
        # 区分線形補間で進行度に対応する目標テンションを求める
        target = points[-1][1]
        for (p0, t0), (p1, t1) in zip(points, points[1:]):
            if p0 <= progress <= p1:
                span = (p1 - p0) or 1.0
                ratio = (progress - p0) / span
                target = t0 + (t1 - t0) * ratio
                break
        else:
            if progress < points[0][0]:
                target = points[0][1]
        deviations.append(abs(known[index] - target * TENSION_SCALE))
    return sum(deviations) / len(deviations)


class NarrativeStructureGate:
    """マクロ骨子の構造ゲート (N2/N3)。

    - off: 何もしない (呼び出し自体をスキップすることを推奨: ``should_run()``)
    - warn: SSOT 物理則で違反検出し、ログ/reporter に報告。骨子は変更しない
    - enforce: 違反検出 + ``GlobalNarrativeBalancer.orchestrate()`` による補正解を
      **tension のみ**骨子へ書き戻す (P6)
    """

    def __init__(
        self,
        settings: Optional[NarrativeStructureSettings] = None,
        balancer: Optional[GlobalNarrativeBalancer] = None,
    ):
        self.settings = settings or load_settings()
        self._balancer = balancer

    @property
    def mode(self) -> str:
        return self.settings.mode

    def should_run(self) -> bool:
        """mode != off のとき True (off での呼び出しコストをゼロにする契約 / Q1)。"""
        return self.mode != "off"

    def run(
        self,
        episodes: Sequence[Any],
        reporter: Any = None,
        tension_curve: Optional[Sequence[Sequence[float]]] = None,
    ) -> StructureGateReport:
        """骨子列を検査 (warn) / 補正 (enforce) する。

        いかなる例外も外へ漏らさない (P3 fail-open)。off と同一の骨子列が
        常に呼び出し側に返ることを契約とする (補正は in-place)。
        ``tension_curve`` (O3) は参照曲線からの逸脱指標の算出にのみ使われ、
        補正・判定には影響しない (advisory)。
        """
        import time

        started = time.perf_counter()
        mode = self.mode
        if mode == "off" or not episodes:
            return StructureGateReport(mode=mode, executed=False)

        sorted_episodes = BeatMapper.sort_episodes(episodes)
        mapper = BeatMapper(self.settings)
        try:
            beats = mapper.to_beats(sorted_episodes)
            violations = detect_tension_violations(beats, self.settings)
            curve_deviation = compute_curve_deviation(beats, tension_curve) if tension_curve else None

            if mode == "warn":
                report = StructureGateReport(
                    mode=mode,
                    executed=True,
                    violation_count=len(violations),
                    violations=violations,
                    curve_deviation=curve_deviation,
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
                self._notify(reporter, report)
                return report

            # enforce: 違反ゼロなら balancer を起こさない (コスト最小化)
            if not violations:
                report = StructureGateReport(
                    mode=mode,
                    executed=True,
                    violation_count=0,
                    curve_deviation=curve_deviation,
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
                self._notify(reporter, report)
                return report

            corrected, error = self._enforce(sorted_episodes, beats)
            # 補正後の骨子から Beat を再構築し、残余違反を検出する
            remaining = detect_tension_violations(
                mapper.to_beats(sorted_episodes),
                self.settings,
            )
            report = StructureGateReport(
                mode=mode,
                executed=True,
                violation_count=len(remaining),
                violations=remaining,
                corrected_episode_count=corrected,
                curve_deviation=curve_deviation,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                error=error,
            )
            self._notify(reporter, report)
            return report
        except Exception as exc:  # noqa: BLE001 - P3: ゲートの失敗で執筆を止めない
            logger.debug("NarrativeStructureGate degraded to off behavior: %s", exc)
            report = StructureGateReport(
                mode=mode,
                executed=False,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )
            return report

    def _enforce(self, sorted_episodes: List[Any], beats: List[Beat]) -> Tuple[int, Optional[str]]:
        """orchestrate による補正解を tension のみ骨子へ書き戻す。"""
        balancer = self._balancer or build_batch_balancer(len(beats))
        integrated = balancer.orchestrate(PlotState.from_beats(beats, total_episodes=len(beats)))
        balanced = integrated.balanced_beats
        if not balanced:
            return 0, "balancer returned no beats"
        changed = BeatMapper(self.settings).apply_tension_back(sorted_episodes, balanced)
        return changed, None

    def _notify(self, reporter: Any, report: StructureGateReport) -> None:
        """違反・補正結果をログと reporter に報告する (執筆は継続)。"""
        if report.violation_count:
            logger.warning(
                "NarrativeStructureGate[%s]: %d tension violation(s): %s",
                report.mode,
                report.violation_count,
                "; ".join(report.violations[:5]),
            )
        elif report.mode == "enforce" and report.corrected_episode_count:
            logger.info(
                "NarrativeStructureGate[enforce]: corrected tension of %d episode(s)",
                report.corrected_episode_count,
            )
        else:
            logger.info("NarrativeStructureGate[%s]: no violations", report.mode)
        if reporter is not None and hasattr(reporter, "report"):
            try:
                if report.violation_count:
                    reporter.report(
                        f"⚠️ 構造ゲート({report.mode}): テンション違反 {report.violation_count} 件を検出"
                        f"{f' / 補正 {report.corrected_episode_count} 話' if report.corrected_episode_count else ''}",
                        "warning",
                    )
                else:
                    reporter.report(f"✅ 構造ゲート({report.mode}): 違反なし", "info")
            except Exception:  # noqa: BLE001 - 報告失敗は無視 (P3)
                pass


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "ENV_MODE_KEY",
    "NarrativeStructureGate",
    "NarrativeStructureSettings",
    "StructureGateReport",
    "BeatMapper",
    "VALID_MODES",
    "build_batch_balancer",
    "compute_curve_deviation",
    "convert_tension",
    "detect_tension_violations",
    "get_gate_mode",
    "get_settings",
    "load_settings",
    "reset_settings_cache",
]
