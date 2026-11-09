"""golden テスト (M1-D: 擾乱スイート出力フォーマット固定)。

MockLLMAdapter で固定応答を返す判定器を使い、suite の出力 JSON 構造が
固定されることを検証する。2回実行しても同じ結果になる（決定性）。
"""

from __future__ import annotations

import asyncio
import json

from tests.mocks.llm_adapter import LLMMocker, MockLLMAdapter

from src.audit.perturbation.suite import JudgeSuite, run_judge_suite

_LONG_TEXT = (
    "アルトは古いダンジョンの入り口に立っていた。剣を握る手に汗が光る。\n\n"
    "「ここだ」とアルトは呟いた。闇が奥から息をしている。\n\n"
    "何かが始まろうとしていた。運命の歯車が回り出す。\n\n"
    "アルトは深呼吸をして、一歩を踏み出した。壁には古い魔法陣が刻まれている。\n\n"
    "この場所は確かに特別な何かを秘めている。扉がゆっくりと開いた。\n\n"
    "冷たい風が吹き込んできた。アルトは息を呑み、剣の柄に手を置いた。\n\n"
    "奥からは微かな音が聞こえる。何かがそこにいる確信があった。\n\n"
    "アルトは前に進む。足音が静かに響く。暗闇の中に視線を感じる。\n\n"
    "扉の向こうには広い部屋が広がっていた。石の床が冷たい。\n\n"
    "中央には祭壇がある。その上に古い書物が置かれている。\n\n"
    "アルトは祭壇に近づき、書物を手に取った。\n"
)


def _make_llm_judge(adapter: MockLLMAdapter):
    """MockLLMAdapter を judge callable にラップする。"""

    def judge(text: str) -> dict[str, float]:
        # 固定応答を JSON として返す想定（generate_text は async なので await）
        response = asyncio.run(
            adapter.generate_text(
                prompt=text, system_prompt="評価してください", max_tokens=2000, temperature=0.2
            )
        )
        try:
            data = json.loads(response)
            return {k: float(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError, TypeError):
            return {"hook": 70.0, "overall": 70.0, "emotional": 70.0, "character_consistency": 70.0}

    return judge


def test_golden_report_structure():
    """固定応答判定器で suite を実行し、レポート構造が固定される。"""
    mocker = LLMMocker()
    mocker.set_responses(
        '{"hook": 80.0, "overall": 70.0, "emotional": 65.0, "character_consistency": 75.0}'
    )
    adapter = MockLLMAdapter(mocker=mocker)
    judge = _make_llm_judge(adapter)

    report = run_judge_suite(
        judge=judge,
        corpus=[_LONG_TEXT],
        judge_id="golden-judge",
        model_name="mock-model",
        prompt_version="v1",
    )

    d = report.to_dict()
    # トップレベルキー
    assert set(d.keys()) == {
        "judge_id", "model_name", "prompt_version", "n_texts",
        "n_transforms", "created_at", "thresholds", "all_passed", "transforms",
    }
    assert d["judge_id"] == "golden-judge"
    assert d["model_name"] == "mock-model"
    assert d["prompt_version"] == "v1"
    assert d["n_texts"] == 1
    assert d["n_transforms"] == 9

    # 各 transform のキー
    for tm in d["transforms"]:
        assert set(tm.keys()) == {
            "transform_id", "kind", "affected_axes", "n_texts",
            "spearman_by_axis", "mean_rho", "identifiability",
            "invariance", "retest_sigma", "all_passed",
        }
        assert tm["transform_id"] in (
            "T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09"
        )
        assert tm["kind"] in ("DIR", "INV")
        assert isinstance(tm["affected_axes"], list)
        assert isinstance(tm["spearman_by_axis"], dict)
        assert isinstance(tm["identifiability"], dict)
        assert isinstance(tm["invariance"], dict)
        assert isinstance(tm["retest_sigma"], dict)
        assert isinstance(tm["all_passed"], bool)


def test_golden_deterministic():
    """同じ judge で2回実行しても結果が同じになる。"""
    def fixed_judge(text: str) -> dict[str, float]:
        return {"hook": 80.0, "overall": 70.0, "emotional": 65.0, "character_consistency": 75.0}

    report1 = run_judge_suite(
        judge=fixed_judge, corpus=[_LONG_TEXT], judge_id="det-judge"
    )
    report2 = run_judge_suite(
        judge=fixed_judge, corpus=[_LONG_TEXT], judge_id="det-judge"
    )

    d1 = report1.to_dict()
    d2 = report2.to_dict()
    # created_at は異なる可能性があるため除外
    d1.pop("created_at")
    d2.pop("created_at")
    assert d1 == d2, "決定性が保証されていない"


def test_golden_json_output():
    """to_json が有効な JSON で、期待フィールドを含む。"""
    mocker = LLMMocker()
    mocker.set_responses(
        '{"hook": 80.0, "overall": 70.0, "emotional": 65.0, "character_consistency": 75.0}'
    )
    adapter = MockLLMAdapter(mocker=mocker)
    judge = _make_llm_judge(adapter)

    report = run_judge_suite(
        judge=judge, corpus=[_LONG_TEXT], judge_id="json-judge"
    )
    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["judge_id"] == "json-judge"
    assert len(parsed["transforms"]) == 9
