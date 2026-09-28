"""V6 監査5件の合格率／全滅率（再執筆率）の**実測**。

V6 ドキュメント §2.1 は「各監査の失敗率が 20%」と仮定し、
据此 5 件全通過 = 0.8^5 ≒ 33%、すなわち約 67% の話数が
全書き直しに回ると論じている。この仮定はいずれも**未検証**であったため、
本モジュールは実際にパイプラインを走らせて数値を出し、仮定値を置き換える。

【重要な読み方】実測値の性質
────────────────────────────────
本テストが測るものは「**パイプライン構造上の**再執筆率」であって、
「**モデル品質としての**失敗率」ではない。理由は以下:

1. 監査5件のうち 4 件（fast_screen / logical / deai / ability）は
   LLM の構造化出力 (``generate_json``) に判定を委譲しているが、
   本テストではネットワーク LLM を呼ばず、決定論的なフェイクを
   **監査器の level で**注入している。``tests/conftest.py`` の
   autouse な ``mock_llm_adapter`` は ``get_llm_adapter`` のみを差すもので、
   監査器コンストラクタへ渡す ``llm`` 引数までは差し替えないため、
   競合するグローバルフィクスチャは追加せず auditors に直接注入する。
2. フェイクの判定基準は「その話の品質が下位 20% なら不合格」という
   校正パラメータであり、これは**仮定そのものであって実測結果ではない**。
   したがって出力される合格率には校正の性質が混入する。
3. 一方「5 件の不合格が **いずれか 1 件でも** 再執筆を発火させる」という
   組み合わせ構造、および各監査内部の実判定ロジック
   （``PlotIntegrityMonitor._verify_causality_chains`` / ``_calculate_score``、
   ``LogicalAuditor._check_base_config`` の repo 参照、
   ``DeAIAuditor`` の角保全チェック）は **実コードそのまま** を通る。
   つまり本テストが置き換えられるのは V6 ドキュメント側の
   「0.8^5 = 33%」「67%」という**算術の前提**であって、
   パイプラインが再執筆を発火させる機構そのものではない。

実モデルの品質に依存する値は別途、実 LLM 運用ログから計測すること。
ここに出力される数値が構造測定である点を混同しないこと。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.agents.audit import DeAIAuditor, LogicalAuditor, PlotIntegrityMonitor
from src.agents.audit_screeners import AbilityConsistencyChecker, FastPlotScreener
from src.models.sharp_edge import SharpEdgeSpec

# 実測対象の話数。V6 計画の要求（>= 8）を満たし、かつ 5% 刻みの
# 合格率が識別できる十分大きい値。
CORPUS_SIZE = 20
CORPUS_SEED = 42

# V6 ドキュメント §2.1 の未検証仮定値。ここに置き換えるための基準値。
ASSUMED_PER_AUDIT_FAILURE_RATE = 0.20
ASSUMED_ALL_PASS_RATE = 0.8**5  # ≒ 0.32768
ASSUMED_REGENERATION_RATIO = 1.0 - ASSUMED_ALL_PASS_RATE

AUDIT_KEYS = (
    "fast_screen",
    "logical_consistency",
    "deai",
    "ability_consistency",
    "causal_integrity",
)


# ---------------------------------------------------------------------------
# 決定論的なフェイク群
# ---------------------------------------------------------------------------


def _stable_unit(*parts: str) -> float:
    """文字列列から [0, 1) の決定論的な値を返す（PYTHONHASHSEED に依存しない）。"""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


@dataclass
class EpisodeSample:
    """1話ぶんの模擬入力（blueprint / drafted_text / context）。"""

    ep_num: int
    quality: float
    blueprint: str
    drafted_text: str
    prev_ctx: str
    settings_json: str
    characters_json: str
    edges: list[SharpEdgeSpec] = field(default_factory=list)


def build_corpus(n: int = CORPUS_SIZE, seed: int = CORPUS_SEED) -> list[EpisodeSample]:
    """決定論的で分散性の高い模擬コーパスを生成する。

    ``quality`` は「その話のプロット品質」を模した [0, 1) の値。
    一部の話だけ blueprint を空にし、``AuditAgent.execute`` における
    ``if blueprint:`` ガード（＝fast_screen のスキップ経路）も実測対象に含める。
    """
    rng = random.Random(seed)
    names = ["カレン", "ルナ", "オールド", "ミア", "セバスチャン", "ノア", "リア", "ダリウス"]
    places = ["王都", "港湾都市", "北の砦", "隠れ家", "学院", "廃鉱山"]
    events = ["覚醒", "彷徨", "再開", "決着", "露見", "崩壊", "誓約"]
    items = ["遺鍵", "欠けた剣", "封じの札", "航海日誌"]

    corpus: list[EpisodeSample] = []
    for i in range(n):
        hero = rng.choice(names)
        place = rng.choice(places)
        event = rng.choice(events)
        item = rng.choice(items)
        has_blueprint = i % 7 != 3

        blueprint = (
            f"第{i + 1}話 蓝图: {hero}は{place}で{item}を入手する。"
            f"対立勢力が現れ、{event}の瞬間が訪れる。"
            f"{hero}は損なわれた réputation を避けるため選択を迫られる。"
            if has_blueprint
            else ""
        )
        key_phrase = f"{item}を"
        drafted = (
            f"{place}の夜、{hero}は静かに歩いた。{item}を握りしめたままだった。"
            f"雨の音が変わった。{event}の気配が漂う。"
            f"誰が先に動くのか、彼はまだ決めていない。"
        )
        corpus.append(
            EpisodeSample(
                ep_num=i + 1,
                quality=rng.random(),
                blueprint=blueprint,
                drafted_text=drafted,
                prev_ctx=f"前話: {hero}は{place}で{item}を得た。",
                settings_json=json.dumps(
                    {"world": place, "power_system": f"{event}力学"}, ensure_ascii=False
                ),
                characters_json=json.dumps(
                    [{"name": hero, "ability": f"{event}Mqzr", "is_alive": True}],
                    ensure_ascii=False,
                ),
                edges=[
                    # NOTE: edge_type は config.sharp_edge_vocabulary.SHARP_EDGE_TYPES
                    # の 4 種のみ有効。DeAIAuditor.audit は emotional_hook を
                    # 自作するが同値は未登録のため必ず ValidationError になる
                    # （src バグ。audit.py:741 参照／本テストでは回避）。
                    SharpEdgeSpec(
                        edge_type="sharp_conflict",
                        description=f"{key_phrase}に込められた重み",
                        key_phrase=key_phrase,
                    )
                ],
            )
        )
    return corpus


class FakeLLM:
    """監査器へ注入する決定論的な LLM フェイク。

    判定は「プロンプト列に紐づく安定ハッシュ」で決まり、再実行しても
    同一結果になる。``reject_threshold``（既定 0.20 = V6 仮定）は
    **校正パラメータ**であり、出力される合格率にこの値が混入することを
    モジュール docstring で明記している。
    """

    def __init__(self, reject_threshold: float = ASSUMED_PER_AUDIT_FAILURE_RATE):
        self.reject_threshold = reject_threshold
        self.call_log: list[tuple[str, bool]] = []

    def _rejects(self, purpose: str, prompt: str) -> bool:
        verdict = _stable_unit(purpose, prompt) < self.reject_threshold
        self.call_log.append((purpose, verdict))
        return verdict

    async def generate_json(self, purpose: str = "", prompt: str = "", **kwargs: Any) -> dict:
        rejects = self._rejects(purpose, prompt)
        if purpose == "causality_extraction":
            # 因果リンクは「候補」を返すだけ。合格・不合格の判定は
            # PlotIntegrityMonitor._verify_causality_chains /
            # _calculate_score の実コードが行う（= 実測）。
            if rejects:
                # 入力はあるが出力のない非終端エンティティ → 鎖切れとして検出される
                return {
                    "metadata": {
                        "causality_links": [
                            {
                                "cause_entity": "破綻した端役",
                                "cause_event": " とある出来",
                                "effect_entity": "終端ならぬ結果",
                                "effect_event": " 二度目の出来",
                                "confidence": 0.9,
                            }
                        ]
                    }
                }
            return {"metadata": {"causality_links": []}}
        return {
            "metadata": {
                "is_valid": not rejects,
                "is_consistent": not rejects,
                "feedback": "STUB-REJECT" if rejects else "OK",
                "suggestions": "",
            }
        }


class FakePromptManager:
    """プロンプトを素通しで組み立てるだけのフェイク（判定そのものは持たない）。"""

    @staticmethod
    def build_fast_plot_screen_prompt(blueprint: str) -> str:
        return f"[fast_plot_screen]\n{blueprint}"

    @staticmethod
    def build_critic_feedback_prompt(
        issue_list: Any = None, draft_content: str = "", blueprint: str = ""
    ) -> str:
        return f"[critic]\n{draft_content}\n{blueprint}"

    @staticmethod
    def build_ability_audit_prompt(blueprint: str, settings_json: str, characters_json: str) -> str:
        return f"[ability_audit]\n{blueprint}\n{settings_json}\n{characters_json}"


class _FakeBibleRepo:
    def __init__(self, scene_integrity: bool):
        self._scene_integrity = scene_integrity

    async def get_plot(self, book_id: int, ep_num: int) -> dict:
        return {
            "scene_integrity": "true" if self._scene_integrity else "false",
            "book_id": book_id,
        }


class _FakePlotRepo:
    async def get_plot(self, book_id: int, ep_num: int) -> Any:
        return {"book_id": book_id, "ep_num": ep_num}


class FakeRepo:
    """``LogicalAuditor`` が必要とする ``repo.bible`` / ``repo.plot`` のみ主讲を持つ。

    ``scene_integrity`` は V6 の設定不整合相当として決定論的に散らす。
    ``_check_character_actions`` / ``_check_theme_continuity`` は src 側で
    スタブ（常に True）なので、ここでは介入しない。
    """

    def __init__(self, scene_integrity: bool):
        self.bible = _FakeBibleRepo(scene_integrity)
        self.plot = _FakePlotRepo()


class FakeExtractionService:
    """``PlotIntegrityMonitor._extraction_service`` の決定論的差し替え。

    実抽出サービスは LLM/GraphRAG を呼ぶため、速度と再現性のため
    エンティティを空で返す（＝未回収伏線・矛盾ゼロ）。因果律判定の
    主要入力である因果リンクは ``FakeLLM`` が供給する。
    """

    async def extract_graph_from_text(self, text: str):
        from src.models.graph_schemas import GraphExtractionResult

        return GraphExtractionResult(entities=[], relationships=[])


# ---------------------------------------------------------------------------
# 実測ハーネス
# ---------------------------------------------------------------------------


@dataclass
class AuditMeasurement:
    """1話ぶんの監査5件の合否。"""

    ep_num: int
    verdicts: dict[str, bool | None]  # None = 監査スキップ（判定なし）

    @property
    def failed(self) -> list[str]:
        return [k for k in AUDIT_KEYS if self.verdicts.get(k) is False]

    @property
    def all_pass(self) -> bool:
        """5件すべてが「不合格ではない」だったか。

        ``AuditAgent.execute`` の実挙動に合わせる: blueprint が空なら
        fast_screen は呼ばれず、不合格カウントに入らない（= 合格扱い）。
        """
        return all(self.verdicts.get(k) is not False for k in AUDIT_KEYS)

    @property
    def triggers_regeneration(self) -> bool:
        return not self.all_pass


async def measure_one_episode(sample: EpisodeSample) -> AuditMeasurement:
    """1話について監査5件を実際に実行し、合否を返す。

    各監査器は ``AuditAgent.__init__`` (src/agents/audit_agent.py:36-44) と
    **同一の引き渡し方**で組み立てる。意図的に src を修正せず、
    現行パイプラインの実挙動をそのまま測る。
    """
    llm = FakeLLM()
    pm = FakePromptManager()

    fast_screener = FastPlotScreener(llm=llm, prompt_manager=pm)
    ability_checker = AbilityConsistencyChecker(llm=llm, prompt_manager=pm)
    deai_auditor = DeAIAuditor(llm=llm, prompt_manager=pm, edge_preserver=None)
    # NOTE: AuditAgent は `PlotIntegrityMonitor()` と `llm` を渡さずに生成する
    # （audit_agent.py:44）。そのため `_extract_causality_links` は
    # 「LLM 未設定」分岐に入り常に [] を返し、スコア 1.0 で**無条件合格**になる。
    # これは src の実バグであり、ここでは忠実に再現する（合格率 100% が実測値）。
    plot_monitor = PlotIntegrityMonitor()
    plot_monitor._extraction_service = FakeExtractionService()

    # 設定不整合は話ごとに決定論的に散らす（＝ロジック監査の失敗源）。
    # 値は src の既定値に合わせて文字列 "true"/"false" を渡す。
    # NOTE: `LogicalAuditor._check_base_config` (audit.py:927) は
    # `if not settings.get("scene_integrity", "false"):` と真偽判定するため、
    # 文字列 "false" も truthy ＝ 常に合格。設定不整合は検出できない（src バグ）。
    scene_integrity = _stable_unit("scene_integrity", str(sample.ep_num)) >= 0.20
    logical_auditor = LogicalAuditor(repo=FakeRepo(scene_integrity), llm=llm, pm=pm)

    verdicts: dict[str, bool | None] = {}

    # 1. fast_screen（blueprint 空なら AuditAgent も呼ばない）
    if sample.blueprint:
        ok, _feedback = await fast_screener.screen_plot(sample.blueprint)
        verdicts["fast_screen"] = bool(ok)
    else:
        verdicts["fast_screen"] = None

    # 2. logical_consistency
    logical_ok, _feedback, _score = await logical_auditor.audit_logical_consistency(
        book_id=1, ep_num=sample.ep_num, blueprint=sample.blueprint
    )
    verdicts["logical_consistency"] = bool(logical_ok)

    # 3. deai（key_phrase は drafted_text に含まれるため角保全は概ね合格）
    deai_ok, _feedback = await deai_auditor.audit(
        content=sample.drafted_text,
        before_content=sample.prev_ctx,
        edges=sample.edges,
        emotional_hook=None,
    )
    verdicts["deai"] = bool(deai_ok)

    # 4. ability_consistency
    ability_ok, _feedback, _suggestions = await ability_checker.audit_ability_consistency(
        blueprint=sample.drafted_text,
        settings_json=sample.settings_json,
        characters_json=sample.characters_json,
    )
    verdicts["ability_consistency"] = bool(ability_ok)

    # 5. causal_integrity
    keywords = await plot_monitor.extract_keywords(sample.drafted_text)
    causal_ok, _score, _failures = await plot_monitor.check_integrity(
        keywords=keywords,
        blueprint=sample.blueprint,
        content=sample.drafted_text,
        threshold=0.7,
    )
    verdicts["causal_integrity"] = bool(causal_ok)

    return AuditMeasurement(ep_num=sample.ep_num, verdicts=verdicts)


@pytest.fixture(scope="module")
def measurements() -> list[AuditMeasurement]:
    """コーパス全話の測定結果を 1 度だけ計算して 3 テストで共有する。"""
    return [asyncio.run(measure_one_episode(s)) for s in build_corpus()]


def _pass_rate(measurements: list[AuditMeasurement], key: str) -> tuple[int, int, float]:
    """(合格数, 判定対象数, 合格率) を返す。スキップ(None)は分母から除外。"""
    judged = [m for m in measurements if m.verdicts.get(key) is not None]
    passed = sum(1 for m in judged if m.verdicts[key] is True)
    rate = (passed / len(judged)) if judged else 0.0
    return passed, len(judged), rate


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


def test_audit_pass_rate_measurement(measurements: list[AuditMeasurement], capsys) -> None:
    """テスト1: 監査5件それぞれの合格率を実測して出力する。"""
    report = {k: _pass_rate(measurements, k) for k in AUDIT_KEYS}

    lines = [
        "=" * 72,
        f"V6 監査5件の合格率【実測】 (STUB 校正値: reject_threshold={ASSUMED_PER_AUDIT_FAILURE_RATE})",
        "=" * 72,
    ]
    for key in AUDIT_KEYS:
        passed, judged, rate = report[key]
        assumed = 1.0 - ASSUMED_PER_AUDIT_FAILURE_RATE
        note = "  ← 不合格 0 件（構造的 no-op の疑い）" if passed == judged else ""
        lines.append(
            f"  {key:<22} 合格 {passed:>2}/{judged:<2} = {rate * 100:6.2f}%"
            f"   (仮定 {assumed * 100:.0f}% / 差 {(rate - assumed) * 100:+.2f}pt){note}"
        )
    lines.append(
        "  合格率が 100% の監査は「その話が一度も落ちなかった」のではなく、"
        "不合格を返す経路が構造的に到達不能である疑いがある。"
    )
    with capsys.disabled():
        print("\n".join(lines))

    # 内部整合性のみを検証する（実測値そのものは問わない）
    for key in AUDIT_KEYS:
        passed, judged, rate = report[key]
        assert 0 <= passed <= judged, f"{key}: 合格数が判定対象数を超過"
        assert 0.0 <= rate <= 1.0, f"{key}: 合格率が [0,1] の範囲外"
        assert judged > 0, f"{key}: 判定対象が 0 件（監査が全てスキップされた）"


def test_all_pass_rate_matches_estimate(measurements: list[AuditMeasurement], capsys) -> None:
    """テスト2: 全5件通過率（= 全滅しない確率）を実測し、V6 仮定 33% と比較する。

    差分(delta)は**測定結果**なので hard-fail させない。assert するのは
    「独立に数えた all_pass 数」と「不合格リストの長さ-derived 数」が
    内部一致することのみ。
    """
    total = len(measurements)
    all_pass_count = sum(1 for m in measurements if m.all_pass)
    measured_all_pass = all_pass_count / total

    # 独立経路: 「不合格が 1 件もない話数」を直接数え直す
    independent_count = sum(1 for m in measurements if len(m.failed) == 0)

    delta = measured_all_pass - ASSUMED_ALL_PASS_RATE
    with capsys.disabled():
        print(
            "\n".join(
                [
                    "=" * 72,
                    "V6 全5件通過率（= 全滅しない確率）【実測】",
                    "=" * 72,
                    f"  実測 all-pass : {all_pass_count}/{total} = {measured_all_pass * 100:6.2f}%",
                    f"  仮定 all-pass : 0.8^5          = {ASSUMED_ALL_PASS_RATE * 100:6.2f}%",
                    f"  差分 (delta)  : {delta * 100:+6.2f} pt",
                    f"  → 再執筆率の実測値は {max(0.0, 1 - measured_all_pass) * 100:.2f}%",
                    "  NOTE: 実測値は STUB 校正値 (reject_threshold=0.20) を含む。",
                ]
            )
        )

    # 断言は内部整合性のみ（delta の大きさでは落とさない）
    assert independent_count == all_pass_count, "all_pass の算出路が2系統で食い違う"
    assert 0.0 <= measured_all_pass <= 1.0
    assert total == CORPUS_SIZE


def test_regeneration_ratio_measurement(measurements: list[AuditMeasurement], capsys) -> None:
    """テスト3: 全滅時に再執筆が発生する話数の割合を実測する（V6 想定 67%）。"""
    total = len(measurements)
    regeneration_count = sum(1 for m in measurements if m.triggers_regeneration)
    measured_ratio = regeneration_count / total

    all_pass_count = sum(1 for m in measurements if m.all_pass)
    expected_ratio = 1.0 - (all_pass_count / total)

    with capsys.disabled():
        print(
            "\n".join(
                [
                    "=" * 72,
                    "V6 再執筆率（= 1 - all-pass）【実測】",
                    "=" * 72,
                    f"  実測 再執筆率 : {regeneration_count}/{total} = {measured_ratio * 100:6.2f}%",
                    f"  仮定 再執筆率 : 1 - 0.8^5      = {ASSUMED_REGENERATION_RATIO * 100:6.2f}%",
                    f"  差分 (delta)  : {(measured_ratio - ASSUMED_REGENERATION_RATIO) * 100:+.2f} pt",
                ]
            )
        )

    # テスト1のデータから導出した 1 - all_pass_rate と厳密に一致すること
    assert measured_ratio == pytest.approx(expected_ratio, abs=1e-12)
    assert regeneration_count + all_pass_count == total
