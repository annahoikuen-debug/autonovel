"""docs/STATUS.md が自己申告しているテスト件数がReality と一致することの検証。

docs/STATUS.md は「このテストは N 件緑」と散文で書いている。
その N がずれると、效果測定表というものの性質（測定値である）が壊れる。
よって **N を実測して照合する**。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATUS = ROOT_DIR / "docs" / "STATUS.md"
# 例: 「`tests/unit/story_spine/test_resolver_no_llm.py`（**7件**緑）」または「（7件緑）」
CLAIM_RE = re.compile(r"`(?P<path>tests/[\w/\-\.]+\.py)`[^`\n]*?（(?:\*\*)?(?P<n>\d+)件(?:\*\*)?緑）")


def _collect(path: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", path, "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=ROOT_DIR,
    )
    # 収集できないtofails。skip すると「収集が壊れている = そもそも検査不能」という
    # 状態で Hawaiiian に this gate が黙って無効化され、doc の嘘が放置される。
    assert proc.returncode == 0, (
        f"{path} を収集できません（returncode={proc.returncode}）: {proc.stdout[-400:]}"
    )
    m = re.search(r"(\d+) tests? collected", proc.stdout)
    return int(m.group(1)) if m else len(re.findall(r"::", proc.stdout))


def test_status_md_contains_measurable_claims():
    """このテストが意味を持つため、対象パターンが 1 つも無い状態を検出すること。"""
    text = STATUS.read_text(encoding="utf-8")
    assert CLAIM_RE.findall(text), (
        "docs/STATUS.md に「（**N件**緑）」形式の自己申告が無い。"
        "本テストが無意味になっている状態を検出する"
    )


@pytest.mark.timeout(1800)
def test_status_md_test_counts_match_reality():
    """自己申告の件数が `pytest --collect-only` の実測と一致すること。

    声明された各パスに対して pytest をサブプロセスで走らせるため、
    実行時間が通常のテストより長い（CI は regression に `--timeout=120` を
    渡すので、このテストだけ明示的に generous な timeout を持つ）。
    """
    text = STATUS.read_text(encoding="utf-8")
    offenders = []
    for m in CLAIM_RE.finditer(text):
        path, claimed = m.group("path"), int(m.group("n"))
        actual = _collect(path)
        if actual != claimed:
            offenders.append(f"{path}: 記載 {claimed} 件 / 実測 {actual} 件")
    assert not offenders, "docs/STATUS.md の件数の記載が Reality と違う:\n" + "\n".join(offenders)


def test_status_md_has_no_unresolved_marker_in_measurement_section():
    """效果測定セクションに未決マーカー（TODO / FIXME / TBD）が残っていないこと。

    これが H0（CI hard gate）を守る本体。将来誰かが書き戻したらここで落ちる。
    """
    text = STATUS.read_text(encoding="utf-8")
    section = text.split("効果測定", 1)[-1]
    offenders = [mk for mk in ("TODO", "FIXME", "TBD", "XXX") if mk in section]
    assert not offenders, f"效果測定セクションに未決マーカーが残存: {offenders}"
