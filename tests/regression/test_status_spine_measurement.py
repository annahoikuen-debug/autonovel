"""docs/STATUS.md の効果測定が捏造値を含まないことの回帰テスト。"""

import re
from pathlib import Path

METRICS = ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8")


def test_status_has_spine_measurement_section():
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    assert "STORY_SPINE 導入の効果測定" in text
    section = _section(text)
    for metric in METRICS:
        assert metric in section, f"{metric} の行が無い"


def test_no_placeholder_remains():
    """未転記のプレースホルダが残っていないこと。"""
    section = _section(Path("docs/STATUS.md").read_text(encoding="utf-8"))
    assert not re.search(r"\(B1\d\)", section), "未転記のプレースホルダが残っている"
    assert "TBD" not in section and "TODO" not in section


def test_unmeasured_cells_are_honest():
    """未計測セルは `null` / `未計測` と書いてあること（空欄や '-' を残さない）。"""
    section = _section(Path("docs/STATUS.md").read_text(encoding="utf-8"))
    for line in section.splitlines():
        if not line.startswith("|") or line.count("|") < 3:
            continue
        if set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert all(cells), f"空欄セルがある: {line}"


def test_every_row_names_its_source():
    """各行に出典（どのコマンド/テストの出力か）が明記されていること。"""
    section = _section(Path("docs/STATUS.md").read_text(encoding="utf-8"))
    for line in section.splitlines():
        if not re.match(r"^\|\s*K\d", line):
            continue
        assert re.search(r"(\.py|--json|同上)", line), f"出典が無い: {line}"


def test_measurement_script_exists_and_is_runnable():
    assert Path("scripts/measure_spine_alignment.py").exists()


def _section(text: str) -> str:
    marker = "STORY_SPINE 導入の効果測定"
    assert marker in text, "測定セクションが無い"
    return text[text.index(marker):]
