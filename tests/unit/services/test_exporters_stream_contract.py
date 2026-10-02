"""各 Exporter の出力が「形式名と一致している」ことの archangel。

現状の事実（2026-10-01 実測 / PLAN_H1 R3）:
- ``EpubExporter`` / ``PdfExporter`` / ``MarkdownExporter`` の 3 类的
  ``export_stream`` はバイト単位で同一で、YAML front matter と ``#`` 見出しを出す。
- つまり **PDF エクスポータが Markdown を返している**。
  正しい修正（PDF ライブラリ導入 or NotImplementedError）は
  tests/unit/services/exporters/ の既存 10 件が「PDF が Markdown を出す」前提を
  持っており、P1（ファイル排他所有）と D12 の制約下では本計画では実施できない。

したがって本テストは「出力の正しさ」ではなく
**「形式名が取り違えられていないことの可視化」**を行う。
既知の欠陥は TODO(H1-9) として明示して固定し、
修正時には本ファイルを反転させる（テストを弱めない）。
"""
from __future__ import annotations

import pytest

from src.services.exporters.base import (
    EpubExporter,
    KakuyomuExporter,
    MarkdownExporter,
    NarouExporter,
    NocturneExporter,
    PdfExporter,
    PlainTextExporter,
)

NOVEL = {"title": "第一話", "synopsis": "あらすじです。", "is_adult": False, "tags": ["x"]}
CHAPTERS = [
    {"ep_num": 1, "title": "始まり", "content": "本文です。"},
    {"ep_num": 2, "title": "続き", "content": "続きの本文です。"},
]


def _out(exporter_cls) -> str:
    return exporter_cls().export(NOVEL, CHAPTERS)


def test_markdown_exporter_emits_markdown_structure():
    out = _out(MarkdownExporter)
    assert out.startswith("---\n"), out
    assert 'title: "第一話"' in out, out
    assert "# 第一話" in out, out
    assert "## 始まり" in out, out


def test_plain_text_exporter_emits_no_markdown():
    out = _out(PlainTextExporter)
    assert "# " not in out, f"プレーンテキストに Markdown 見出しが混入している: {out!r}"
    assert "◆ 始まり ◆" in out, out


def test_narou_exporter_uses_narou_page_break():
    out = _out(NarouExporter)
    assert "\n=====\n" in out, f"なろうの話区切りが無い: {out!r}"


def test_kakuyomu_exporter_uses_level3_headings():
    import re

    out = _out(KakuyomuExporter)
    assert "### 始まり" in out, out
    assert not re.search(r"^## 始まり$", out, re.M), f"カクヨムは level2 見出しを使わない: {out!r}"


def test_nocturne_exporter_emits_age_gate_notice():
    out = _out(NocturneExporter)
    assert "[年齢確認: 18歳以上であることを確認しました]" in out, out


@pytest.mark.parametrize("exporter_cls", [MarkdownExporter, EpubExporter, PdfExporter])
def test_markdown_family_shares_one_renderer(exporter_cls):
    """3 クラスが同じテンプレートを使うことで、重複が再発生しないこと。"""
    import inspect

    src = inspect.getsource(exporter_cls.export_stream)
    assert "_render_markdown_stream" in src, (
        f"{exporter_cls.__name__}.export_stream が共通レンダラを使っていない（重複の再発生）"
    )


def test_pdf_exporter_markdown_leak_is_known_and_pinned():
    """既知の欠陥の固定: PDF は Markdown を返している（TODO(H1-9)）。

    ``assert !=`` にすると既存 10 件のテストと衝突するため、
    ここでは「欠陥が今この形である」ことを明示的に固定する。
    修正時にこのテストを ``!=`` へ反転させること。
    """
    pdf_out = _out(PdfExporter)
    md_out = _out(MarkdownExporter)
    assert pdf_out == md_out, (
        "PdfExporter の出力が MarkdownExporter と異なった。"
        " TODO(H1-9) を解消したなら、本テストを != に反転させること。"
    )
    assert "# " in pdf_out, "PdfExporter は既知のとおり Markdown 見出しを出している（H1-9）"


def test_epub_exporter_markdown_leak_is_known_and_pinned():
    """既知の欠陥の固定: EPUB も Markdown を返している（TODO(H1-9)）。"""
    epub_out = _out(EpubExporter)
    assert epub_out.startswith("---\n"), epub_out
    assert "# 第一話" in epub_out, epub_out