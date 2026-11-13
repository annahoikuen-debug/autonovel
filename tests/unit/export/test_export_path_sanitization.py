"""Step 15 (H14): エクスポート書き出しパス無害化。

H14: multimedia_service.py 等が series.title を無害化せずにパス結合し、
../ による出力ディレクトリ外への書き出しが可能だった。
修正：sanitize_filename でパス区切り文字と .. を除去。
"""
from __future__ import annotations

from src.backend.multimedia_service import sanitize_filename


def test_sanitize_filename_blocks_dotdot():
    """../ は除去・置換され、パスを抜けられない（H14）。"""
    assert sanitize_filename("../evil") == "___evil"


def test_sanitize_filename_blocks_path_separators():
    """/ と \ はアンダースコアに置換される（H14）。"""
    assert sanitize_filename("a/b") == "a_b"
    assert sanitize_filename("a\\b") == "a_b"


def test_sanitize_filename_allows_normal_chars():
    """通常の文字はそのまま（正常系回帰）。"""
    assert sanitize_filename("私の本_第1話") == "私の本_第1話"
