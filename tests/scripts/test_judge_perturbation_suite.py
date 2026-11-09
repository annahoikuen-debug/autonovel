"""CLI テスト (M1-D: judge_perturbation_suite.py)。

main() を直接呼び出し、擾乱スイート CLI が正しく動作することを検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.judge_perturbation_suite import main, _make_judge  # noqa: E402


def _write_corpus(tmp_path: Path, n_files: int = 2) -> Path:
    """テスト用コーパスディレクトリを作成し、そのパスを返す。"""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for i in range(n_files):
        (corpus_dir / f"ep{i}.txt").write_text(
            f"アルトはダンジョンに入った。剣を握った。話{i}。\n\n何かが始まる。\n",
            encoding="utf-8",
        )
    return corpus_dir


def test_main_runs_and_returns_zero(tmp_path):
    """main が正常終了し、レポート JSON を出力する。"""
    corpus_dir = _write_corpus(tmp_path, n_files=2)
    out_path = tmp_path / "report.json"

    rc = main(
        [
            "--corpus",
            str(corpus_dir / "*.txt"),
            "--judge",
            "mock",
            "--model",
            "test-model",
            "--prompt-version",
            "v1",
            "--out",
            str(out_path),
        ]
    )
    # モック判定器では Spearman ρ が 0 になり all_passed=False となるため、
    # 終了コードは 0 または 1 のいずれか。重要なのはレポートが出力されること。
    assert rc in (0, 1)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["judge_id"] == "mock"
    assert data["n_texts"] == 2
    assert data["n_transforms"] == 9
    assert "transforms" in data
    assert len(data["transforms"]) == 9


def test_main_corpus_limit(tmp_path):
    """--corpus-limit がコーパス数を制限する。"""
    corpus_dir = _write_corpus(tmp_path, n_files=5)
    out_path = tmp_path / "report_limit.json"

    rc = main(
        [
            "--corpus",
            str(corpus_dir / "*.txt"),
            "--judge",
            "mock",
            "--out",
            str(out_path),
            "--corpus-limit",
            "2",
        ]
    )
    assert rc in (0, 1)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["n_texts"] == 2


def test_make_judge_mock():
    """_make_judge('mock') が dict を返す callable を返す。"""
    judge = _make_judge("mock")
    result = judge("テキスト。")
    assert isinstance(result, dict)
    assert "hook" in result
    assert "overall" in result


def test_make_judge_unknown_raises():
    """不明な判定器種別で ValueError が出る。"""
    with pytest.raises(ValueError):
        _make_judge("nonexistent")


def test_main_missing_corpus_returns_nonzero(tmp_path):
    """コーパスが空の場合、main は非ゼロを返す。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    rc = main(
        ["--corpus", str(empty_dir / "*.txt"), "--judge", "mock"]
    )
    assert rc == 1
