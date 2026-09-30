"""コスト計測CLIの出力契約の回帰テスト。

T6 Step 6 の回帰防止。

`docs/STATUS.md` の効果測定表が読むため、レポートのキー集合は
**変更しない**契約として固定する。
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.report_episode_cost import (  # noqa: E402
    REPORT_KEYS,
    aggregate_records,
    build_episode_row,
    build_report,
)

ROOT = Path(__file__).resolve().parents[3]


def _seed(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE token_usage (ep_num INTEGER, book_id INTEGER,"
        " task_type TEXT, model_name TEXT, tier TEXT,"
        " input_tokens INTEGER, output_tokens INTEGER)"
    )
    conn.executemany(
        "INSERT INTO token_usage VALUES (?,?,?,?,?,?,?)",
        [
            (1, 1, "writing", "claude-3-5-haiku", "tier2_standard", 12000, 2400),
            (1, 1, "audit", "gemini-2.0-flash", "tier1_light", 8000, 900),
            (2, 1, "writing", "claude-3-5-sonnet", "tier3_premium", 15000, 3000),
        ],
    )
    conn.commit()
    conn.close()


# ── 集計ロジック ──────────────────────────────────────────────────


def test_report_keys_are_stable():
    """1話レポートの必須キーが揃っていること（出力契約の固定）。"""
    row = build_episode_row(
        {
            "ep_num": 1,
            "input_tokens": 1000,
            "output_tokens": 500,
            "model_name": "claude-3-5-haiku",
            "task_type": "audit",
            "tier": "tier1_light",
        }
    )
    assert set(REPORT_KEYS) <= set(row), f"欠落キー: {set(REPORT_KEYS) - set(row)}"


def test_cost_is_computed_from_registered_pricing():
    """コストが MODEL_PRICING から算出されること（0 の黙認をしない）。"""
    row = build_episode_row(
        {
            "ep_num": 1,
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "model_name": "claude-3-5-haiku",
            "task_type": "writing",
        }
    )
    assert row["total_cost_usd"] > 0, "既知モデルでも $0 として計上されている"


def test_unknown_model_is_flagged_not_silently_zero():
    """未知モデルは 0 になるが、task/tier バケットには入る（行ごと消えない）。"""
    row = build_episode_row(
        {
            "ep_num": 1,
            "input_tokens": 1000,
            "output_tokens": 500,
            "model_name": "unknown-xyz",
            "task_type": "writing",
        }
    )
    assert row["llm_calls"] == 1
    assert "writing" in row["by_task"]


def test_aggregate_groups_by_episode():
    records = [
        {"ep_num": 1, "input_tokens": 100, "output_tokens": 10,
         "model_name": "gpt-4o-mini", "task_type": "writing"},
        {"ep_num": 1, "input_tokens": 200, "output_tokens": 20,
         "model_name": "gpt-4o-mini", "task_type": "audit"},
        {"ep_num": 2, "input_tokens": 50, "output_tokens": 5,
         "model_name": "gpt-4o-mini", "task_type": "writing"},
    ]
    rows = aggregate_records(records)
    assert [r["ep_num"] for r in rows] == [1, 2]
    assert rows[0]["llm_calls"] == 2
    assert rows[0]["total_tokens"] == 330
    assert rows[1]["llm_calls"] == 1


def test_records_without_episode_are_skipped():
    assert aggregate_records([{"input_tokens": 1, "output_tokens": 1}]) == []


def test_totals_include_usd_per_episode():
    """効果測定表が読む `usd_per_episode` が算出されること。"""
    records = [
        {"ep_num": 1, "input_tokens": 1000, "output_tokens": 100,
         "model_name": "gpt-4o-mini", "task_type": "writing"},
        {"ep_num": 2, "input_tokens": 1000, "output_tokens": 100,
         "model_name": "gpt-4o-mini", "task_type": "writing"},
    ]
    report = build_report(records)
    assert report["totals"]["episode_count"] == 2
    assert report["totals"]["usd_per_episode"] == pytest.approx(
        report["totals"]["total_cost_usd"] / 2
    )


# ── CLI 実挙動 ───────────────────────────────────────────────────


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """CLI を UTF-8 前提で実行する。

    Windows の既定エンコーディング（cp932）は日本語出力をデコードできないため、
    `PYTHONIOENCODING` を明示する。CLI 側の出力自体は UTF-8 前提。
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True, text=True, cwd=ROOT, env=env, encoding="utf-8",
    )


def test_cli_emits_valid_json(tmp_path):
    """--json フラグで機械可読な出力が得られること。"""
    db = tmp_path / "cost.db"
    _seed(db)
    result = _run_cli(
        "scripts/report_episode_cost.py", "--json", "--db", str(db)
    )
    assert result.returncode == 0, f"CLI が失敗: {result.stderr}"
    payload = json.loads(result.stdout)
    assert "episodes" in payload
    assert len(payload["episodes"]) == 2
    assert payload["totals"]["llm_calls"] == 3


def test_cli_without_db_prints_empty_report():
    """DB 未指定でも壊れず、空レポートを返すこと。"""
    result = _run_cli("scripts/report_episode_cost.py", "--json")
    assert result.returncode == 0, f"CLI が失敗: {result.stderr}"
    assert json.loads(result.stdout)["episodes"] == []


def test_cli_missing_db_file_is_not_fatal(tmp_path):
    """存在しないDBパスを渡してもクラッシュしないこと。"""
    result = _run_cli(
        "scripts/report_episode_cost.py", "--json", "--db", str(tmp_path / "nope.db")
    )
    assert result.returncode == 0, f"CLI が失敗: {result.stderr}"
    assert json.loads(result.stdout)["episodes"] == []


def test_cli_episode_filter(tmp_path):
    """--episodes による絞り込みが効くこと。"""
    db = tmp_path / "cost.db"
    _seed(db)
    result = _run_cli(
        "scripts/report_episode_cost.py", "--json", "--db", str(db), "--episodes", "2"
    )
    payload = json.loads(result.stdout)
    assert [e["ep_num"] for e in payload["episodes"]] == [2]


def test_cli_text_mode_renders_table(tmp_path):
    """テキスト形式でも1話=$/回数の列が並ぶこと。"""
    db = tmp_path / "cost.db"
    _seed(db)
    result = _run_cli("scripts/report_episode_cost.py", "--db", str(db))
    assert result.returncode == 0
    assert "ep_num" in result.stdout
    assert "calls" in result.stdout
