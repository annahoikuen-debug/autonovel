"""統合テスト失敗数ラケットの基準ファイル 構造健全性テスト.

このテストは「0件の失敗（ゲート化完了）」を機械が判定できる数値として固定し、
以後どのステップでも失敗数が増えると即座に赤くなるための
背骨となる。

失敗数そのものは CI 上（postgres/redis あり）で検証するため、
本テストは基準ファイルの構造健全性のみを担う。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BASELINE_PATH = Path("config/integration_failure_baseline.json")


def _load_baseline() -> dict:
    assert BASELINE_PATH.is_file(), f"{BASELINE_PATH} が見つかりません"
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_baseline_file_exists_and_structure_valid() -> None:
    data = _load_baseline()
    assert isinstance(data, dict)
    assert isinstance(data.get("baseline_commit"), str)
    assert isinstance(data.get("max_failed"), int)
    assert isinstance(data.get("known_failures"), list)
    assert isinstance(data.get("gate_target_failed"), int)


def test_max_failed_is_at_least_gate_target() -> None:
    data = _load_baseline()
    assert data["max_failed"] >= data["gate_target_failed"]


def test_known_failures_count_and_format() -> None:
    data = _load_baseline()
    failures = data["known_failures"]
    # ゲート化後は known_failures は空配列（1件も許容しない）
    assert len(failures) == 0, f"known_failures は空配列であるべきだが {len(failures)} 件"
    for item in failures:
        assert isinstance(item, str)
        assert item.startswith("tests/"), f"'tests/' で始まらない: {item}"
        assert "::" in item, f"'::' を含まない: {item}"


def test_known_failures_have_no_duplicates() -> None:
    data = _load_baseline()
    failures = data["known_failures"]
    assert len(failures) == len(set(failures)), "known_failures に重複がある"
