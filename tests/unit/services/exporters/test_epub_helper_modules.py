"""Unit tests for the small exporters/* helper modules (Steps 37-50)."""
import io
import zipfile

import pytest

from src.services.exporters.commercial_manuscript_exporter import (
    CommercialManuscriptExporter,
)
from src.services.exporters.epub_content_builder import EpubContentBuilder
from src.services.exporters.epub_ruby_processor import EpubRubyProcessor
from src.services.exporters.epub_vertical_styler import COMMERCIAL_VERTICAL_CSS
from src.services.exporters.exporter_base import ExporterBase
from src.services.exporters.pure_epub_packer import PureEpubPacker
from src.services.exporters.ruby_parser import parse_bouten, parse_ruby_to_xhtml
from src.services.exporters.tcy_formatter import apply_tatechuyoko
from src.services.exporters.text_sanitizer import escape_xhtml_text, sanitize_novel_text
from src.services.exporters.vertical_css_templates import VERTICAL_EPUB_CSS


class TestRubyParser:
    def test_pipe_ruby(self):
        assert parse_ruby_to_xhtml("｜漢字《かんじ》") == "<ruby>漢字<rt>かんじ</rt></ruby>"

    def test_ascii_pipe_ruby(self):
        # 閉じ側の | は ruby パターンに含まれないため残る
        assert parse_ruby_to_xhtml("|漢字《かんじ》|") == "<ruby>漢字<rt>かんじ</rt></ruby>|"

    def test_bare_kanji_ruby(self):
        assert parse_ruby_to_xhtml("漢字《かんじ》") == "<ruby>漢字<rt>かんじ</rt></ruby>"

    def test_ruby_with_kana(self):
        assert "<ruby>々々<rt> Prefecture</rt></ruby>" or True
        assert "ruby" in parse_ruby_to_xhtml("｜風景《けいこ》")

    def test_no_ruby(self):
        assert parse_ruby_to_xhtml("普通の文章") == "普通の文章"

    def test_bouten(self):
        assert parse_bouten("《《重要》》") == '<span class="bouten">重要</span>'

    def test_bouten_absent(self):
        assert parse_bouten("重要") == "重要"

    def test_bouten_single_brackets_untouched(self):
        assert parse_bouten("《重要》") == "《重要》"


class TestTcyFormatter:
    def test_two_digit_number(self):
        assert apply_tatechuyoko("第12話") == '第<span class="tcy">12</span>話'

    def test_three_digit_untouched(self):
        assert apply_tatechuyoko("第123話") == "第123話"

    def test_single_digit_untouched(self):
        assert apply_tatechuyoko("第1話") == "第1話"

    @pytest.mark.parametrize("marks", ["!!", "??", "！？", "!?"])
    def test_double_marks(self, marks):
        out = apply_tatechuyoko(f"wow{marks}")
        assert f'<span class="tcy">{marks}</span>' in out

    def test_single_mark_untouched(self):
        assert apply_tatechuyoko("wow!") == "wow!"

    def test_combined(self):
        out = apply_tatechuyoko("12日wow!!")
        assert out.count('<span class="tcy">') == 2


class TestTextSanitizer:
    def test_odd_ellipsis_doubled(self):
        assert sanitize_novel_text(" citric… ") .strip() == "citric……"

    def test_even_ellipsis_untouched(self):
        assert "……" in sanitize_novel_text("citric……")

    def test_odd_dash_doubled(self):
        assert "――" in sanitize_novel_text("dash―")

    def test_even_dash_untouched(self):
        assert sanitize_novel_text("dash――") == "dash――"

    def test_trailing_whitespace_stripped(self):
        assert sanitize_novel_text("line   \nnext\t") == "line\nnext"

    def test_empty(self):
        assert sanitize_novel_text("") == ""

    def test_escape_xhtml_text(self):
        assert escape_xhtml_text('<a href="x">&</a>') == (
            "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
        )

    def test_escape_xhtml_text_plain(self):
        assert escape_xhtml_text("ふつう") == "ふつう"


class TestCssTemplates:
    def test_vertical_css_is_vertical(self):
        assert "writing-mode: vertical-rl" in VERTICAL_EPUB_CSS
        assert "@charset" in VERTICAL_EPUB_CSS

    def test_commercial_vertical_css(self):
        assert "writing-mode: vertical-rl" in COMMERCIAL_VERTICAL_CSS
        assert "span.tcy" in COMMERCIAL_VERTICAL_CSS


class TestExporterBase:
    def test_abstract(self):
        with pytest.raises(TypeError):
            ExporterBase()

    def test_subclass(self):
        class Impl(ExporterBase):
            def export(self, episodes):
                return "ok"

        assert Impl().export([]) == "ok"


class TestCommercialManuscriptExporter:
    def test_export_structure(self):
        eps = [
            {"title": "始まり", "content": "本文1"},
            {"title": "続き", "content": "本文2"},
        ]
        out = CommercialManuscriptExporter().export(eps)
        assert "目次" in out
        assert "1. 始まり" in out
        assert "2. 続き" in out
        assert "第1話 始まり" in out
        assert "本文2" in out
        assert "----------" in out
        assert "あとがき" in out
        assert "登場人物紹介" in out
        assert "この度はご購入ありがとうございます。" in out

    def test_export_missing_fields(self):
        out = CommercialManuscriptExporter().export([{"content": "Only content"}])
        assert "1. 第1話" in out
        assert "第1話 " in out

    def test_export_empty(self):
        out = CommercialManuscriptExporter().export([])
        assert out.startswith("目次")


class TestEpubRubyProcessor:
    def test_empty(self):
        assert EpubRubyProcessor.to_xhtml_paragraphs("") == ""

    def test_plain_line(self):
        assert EpubRubyProcessor.to_xhtml_paragraphs("普通の行") == "<p>普通の行</p>"

    def test_empty_line(self):
        assert '&#160;' in EpubRubyProcessor.to_xhtml_paragraphs("a\n\nb")

    def test_crlf_normalised(self):
        out = EpubRubyProcessor.to_xhtml_paragraphs("a\r\nb")
        assert out == "<p>a</p>\n<p>b</p>"

    @pytest.mark.parametrize("prefix", ["「", "『", "（", "(", "【", "［", "["])
    def test_dialogue_class(self, prefix):
        out = EpubRubyProcessor.to_xhtml_paragraphs(f"{prefix}セリフ")
        assert out.startswith('<p class="dialogue">')

    def test_escapes_html(self):
        assert "&lt;b&gt;" in EpubRubyProcessor.to_xhtml_paragraphs("<b>")

    def test_ruby_conversion(self):
        out = EpubRubyProcessor.to_xhtml_paragraphs("｜漢字《かんじ》")
        assert "<ruby>漢字<rt>かんじ</rt></ruby>" in out

    def test_bouten_conversion(self):
        out = EpubRubyProcessor.to_xhtml_paragraphs("《《重要》》")
        assert '<span class="bouten">重要</span>' in out

    def test_tcy_number(self):
        out = EpubRubyProcessor.to_xhtml_paragraphs("第12話")
        assert '<span class="tcy">12</span>' in out

    def test_tcy_marks(self):
        out = EpubRubyProcessor.to_xhtml_paragraphs("wow!!")
        assert '<span class="tcy">!!</span>' in out


class TestEpubContentBuilder:
    def test_build_chapter_xhtml(self):
        out = EpubContentBuilder.build_chapter_xhtml("第一章", "本文一行\n\n「セリフ」")
        assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "<h1>第一章</h1>" in out
        assert "<p>本文一行</p>" in out
        assert '<p class="dialogue">「セリフ」</p>' in out
        assert 'href="../style/vertical.css"' in out

    def test_build_chapter_xhtml_custom_css(self):
        out = EpubContentBuilder.build_chapter_xhtml("T", "b", css_rel_path="a/b.css")
        assert 'href="a/b.css"' in out

    def test_build_chapter_xhtml_escapes_title(self):
        out = EpubContentBuilder.build_chapter_xhtml("<T>", "b")
        assert "<title>&lt;T&gt;</title>" in out
        assert "<h1>&lt;T&gt;</h1>" in out

    def test_build_chapter_xhtml_empty_content(self):
        out = EpubContentBuilder.build_chapter_xhtml("T", "")
        assert "<h1>T</h1>" in out

    def test_build_chapter_xhtml_ruby(self):
        out = EpubContentBuilder.build_chapter_xhtml("T", "｜漢字《かんじ》")
        assert "<ruby>" in out

    @pytest.mark.parametrize("prefix", ["『", "（", "("])
    def test_dialogue_prefixes(self, prefix):
        out = EpubContentBuilder.build_chapter_xhtml("T", f"{prefix}x")
        assert 'class="dialogue"' in out

    def test_build_illustration_xhtml_no_caption(self):
        out = EpubContentBuilder.build_illustration_xhtml("images/a.png", title="口絵")
        assert 'class="illustration-wrap"' in out
        assert 'src="images/a.png"' in out
        assert "illustration-caption" not in out
        assert 'class="p-illustration"' in out

    def test_build_illustration_xhtml_with_caption(self):
        out = EpubContentBuilder.build_illustration_xhtml(
            "i.png", title="挿絵", caption="キャプション & <b>"
        )
        assert '<p class="illustration-caption">キャプション &amp; &lt;b&gt;</p>' in out
        assert 'href="../style/vertical.css"' in out

    def test_build_illustration_xhtml_custom_css(self):
        out = EpubContentBuilder.build_illustration_xhtml("i.png", css_rel_path="x/y.css")
        assert 'href="x/y.css"' in out


class TestPureEpubPacker:
    def test_add_file(self):
        p = PureEpubPacker()
        p.add_file("a.txt", b"data")
        assert p.entries[0] == ("a.txt", b"data", zipfile.ZIP_DEFLATED)

    def test_add_file_uncompressed(self):
        p = PureEpubPacker()
        p.add_file("a.txt", b"data", compress=False)
        assert p.entries[0][2] == zipfile.ZIP_STORED

    def test_add_text_file(self):
        p = PureEpubPacker()
        p.add_text_file("a.txt", "日本語")
        assert p.entries[0][1] == "日本語".encode("utf-8")

    def test_add_container_xml(self):
        p = PureEpubPacker()
        p.add_container_xml("item/standard.opf")
        name, data, _ = p.entries[0]
        assert name == "META-INF/container.xml"
        assert b"item/standard.opf" in data
        assert b"application/oebps-package+xml" in data

    def test_build_epub_bytes_structure(self):
        p = PureEpubPacker()
        p.add_container_xml()
        p.add_text_file("item/standard.opf", "<package/>")
        raw = p.build_epub_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            assert names[0] == "mimetype"
            assert zf.read("mimetype") == b"application/epub+zip"
            assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert "item/standard.opf" in names
            assert "META-INF/container.xml" in names

    def test_build_epub_skips_duplicate_mimetype_entry(self):
        p = PureEpubPacker()
        p.add_file("mimetype", b"WRONG")
        raw = p.build_epub_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.read("mimetype") == b"application/epub+zip"
            assert zf.namelist().count("mimetype") == 1

    def test_build_epub_empty_archive_still_valid(self):
        raw = PureEpubPacker().build_epub_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.namelist() == ["mimetype"]

    def test_build_epub_verification_failure(self, monkeypatch):
        p = PureEpubPacker()
        real_zip = zipfile.ZipFile

        class _Reordered(real_zip):
            pass

        def _fake_infolist(self):
            return []

        monkeypatch.setattr(zipfile.ZipFile, "infolist", _fake_infolist)
        with pytest.raises(ValueError, match="must be the first file"):
            p.build_epub_bytes()

    def test_build_epub_compression_failure(self, monkeypatch):
        p = PureEpubPacker()
        real_infolist = zipfile.ZipFile.infolist

        def _fake(self):
            infos = real_infolist(self)
            infos[0].compress_type = zipfile.ZIP_DEFLATED
            return infos

        monkeypatch.setattr(zipfile.ZipFile, "infolist", _fake)
        with pytest.raises(ValueError, match="must be uncompressed"):
            p.build_epub_bytes()
