"""README の起動手順が start_local.ps1 を参照していることを検証する。

TRACK-R R1: 起動エントリの一本化と .bat の非推奨化に伴う回帰テスト。
README の起動手順が scripts/start_local.ps1 を参照していることを assert し、
文書の陳腐化を検出する。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


def test_readme_mentions_start_local_ps1():
    """README に scripts/start_local.ps1 への起動手順が記載されていること."""
    content = README.read_text(encoding="utf-8")
    assert "start_local.ps1" in content, (
        "README に scripts/start_local.ps1 への参照が見つかりません。"
        "起動手順の一本化に合わせて README も更新してください。"
    )


def test_readme_does_not_recommend_bat_files():
    """README が .bat ファイルを主要な起動手順として推奨していないこと."""
    content = README.read_text(encoding="utf-8")
    # 「アプリ起動.bat」を「ダブルクリック」で実行する記述は非推奨化対象
    assert "アプリ起動_ローカル.bat`** をダブルクリック" not in content, (
        "README に .bat ファイルをダブルクリックする起動手順が残っています。"
        "start_local.ps1 への誘導に変更してください。"
    )


def test_readme_mentions_start_local_as_primary():
    """README が start_local.ps1 を主要な起動手順として推奨していること."""
    content = README.read_text(encoding="utf-8")
    # start_local.ps1 が「推奨」または「主要」として言及されていること
    assert "start_local.ps1" in content
    assert "非推奨" in content or "推奨" in content, (
        "README に .bat ファイルの非推奨化または start_local.ps1 の推奨記載が見つかりません。"
    )
