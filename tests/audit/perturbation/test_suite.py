"""T-S1: 擾乱スイートオーケストレータテスト。

JudgeSuite / run_judge_suite が正しく動作することを検証する。
"""

from __future__ import annotations

from src.audit.perturbation.suite import JudgeSuite, JudgeSuiteReport, run_judge_suite

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


def _fixed_judge(text: str) -> dict[str, float]:
    """テキスト長によらず固定スコアを返す判定器。"""
    return {
        "hook": 80.0,
        "overall": 70.0,
        "emotional": 65.0,
        "character_consistency": 75.0,
    }


def test_judge_suite_run_returns_report():
    """JudgeSuite.run が JudgeSuiteReport を返す。"""
    suite = JudgeSuite(judge=_fixed_judge, judge_id="test-judge")
    report = suite.run([_LONG_TEXT])
    assert isinstance(report, JudgeSuiteReport)
    assert report.judge_id == "test-judge"
    assert report.n_texts == 1
    assert report.n_transforms == 9


def test_run_judge_suite_convenience():
    """run_judge_suite 便利関数が動作する。"""
    report = run_judge_suite(
        judge=_fixed_judge,
        corpus=[_LONG_TEXT],
        judge_id="convenience-judge",
        model_name="test-model",
        prompt_version="v1",
    )
    assert report.judge_id == "convenience-judge"
    assert report.model_name == "test-model"
    assert report.prompt_version == "v1"
    assert report.n_texts == 1


def test_report_structure():
    """レポートの各フィールドが期待通りの構造である。"""
    report = run_judge_suite(_fixed_judge, [_LONG_TEXT], judge_id="struct-judge")
    d = report.to_dict()
    assert d["judge_id"] == "struct-judge"
    assert d["n_texts"] == 1
    assert d["n_transforms"] == 9
    assert isinstance(d["created_at"], str)
    assert isinstance(d["thresholds"], dict)
    assert d["thresholds"]["rho_threshold"] == 0.8
    assert len(d["transforms"]) == 9
    for tm in d["transforms"]:
        assert "transform_id" in tm
        assert "kind" in tm
        assert "affected_axes" in tm
        assert "n_texts" in tm
        assert "spearman_by_axis" in tm
        assert "mean_rho" in tm
        assert "identifiability" in tm
        assert "invariance" in tm
        assert "retest_sigma" in tm
        assert "all_passed" in tm


def test_report_json_serializable():
    """to_json が有効な JSON 文字列を返す。"""
    report = run_judge_suite(_fixed_judge, [_LONG_TEXT], judge_id="json-judge")
    json_str = report.to_json()
    assert isinstance(json_str, str)
    assert '"judge_id": "json-judge"' in json_str
    assert '"transforms"' in json_str


def test_empty_corpus():
    """空コーパスでも例外を出さない。"""
    report = run_judge_suite(_fixed_judge, [], judge_id="empty-judge")
    assert report.n_texts == 0
    assert report.n_transforms == 9
    for tm in report.transform_metrics:
        assert tm.n_texts == 0


def test_judge_exception_handled():
    """判定器が例外を出した場合もスイートは継続する。"""
    def failing_judge(text: str) -> dict[str, float]:
        raise RuntimeError("judge failure")

    report = run_judge_suite(failing_judge, [_LONG_TEXT], judge_id="fail-judge")
    assert report.n_texts == 1
    assert report.n_transforms == 9
    # 全変換が処理され、クラッシュしない
