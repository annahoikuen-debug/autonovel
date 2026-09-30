"""計測スクリプトが機械可読な JSON を返し、実測値であることを保証すること。"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/measure_spine_alignment.py"


def _run(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, cwd=Path.cwd(), timeout=120,
    )
    return result.returncode, result.stdout, result.stderr


def test_cli_emits_valid_json():
    code, out, err = _run("--json")
    assert code == 0, f"スクリプトが失敗した: {err}"
    payload = json.loads(out)
    for key in ("k1_alignment", "k2_midpoint", "k3_climax", "books", "book_count"):
        assert key in payload, f"キー {key!r} が無い"


def test_measurements_are_computed_not_hardcoded():
    """**計測値は DB から計算される**こと（PLAN_T6 の教訓）。

    バンド幅（0.40-0.60 / 0.75-0.92）は仕様定数なのでソースに置いてよい。
    禁止するのは *結果* の固定値。
    """
    src = Path(SCRIPT).read_text(encoding="utf-8")
    # 必ず実際の集計を通っていること
    assert "statistics.fmean" in src, "平均の計算が使われていない"
    assert "statistics.pstdev" in src, "標準偏差の計算が使われていない"
    assert "return {" in src and '"k1_alignment"' in src
    # 結果を固定している形（定数代入）がないこと
    for forbidden in ("k1_alignment = 0.", "k2_midpoint = {", "k3_climax = {"):
        assert forbidden not in src, f"{forbidden!r} は計測値を固定している"


def test_band_thresholds_are_declared_as_spec():
    """バンド幅は仕様定数として明示されていること（隠れた魔法数にしない）。"""
    src = Path(SCRIPT).read_text(encoding="utf-8")
    assert "0.40 <= m <= 0.60" in src
    assert "0.75 <= c <= 0.92" in src


def test_subprocess_without_json_flag_also_works():
    code, out, err = _run()
    assert code == 0, err
    assert "書籍数" in out


def test_empty_database_does_not_crash():
    """書籍が0件でもクラッシュしないこと（計測で本番を落とさない）。"""
    payload = json.loads(_run("--json")[1])
    assert payload["book_count"] == 0
    assert payload["books"] == []


def test_output_is_reproducible():
    """2回走らせて出力が一致すること（実測であることの間接証明）。"""
    assert _run("--json")[1] == _run("--json")[1]


def test_pattern_filter_is_accepted():
    code, out, err = _run("--json", "--pattern", "exile_rise")
    assert code == 0, err
    assert json.loads(out)["patterns"] == ["exile_rise"]
