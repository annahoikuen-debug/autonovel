"""Extended tests for src/services/exporters/base.py exporters and filters."""
import pytest

from src.services.exporters.base import (
    BaseExporter,
    EpubExporter,
    KakuyomuExporter,
    MarkdownExporter,
    NarouExporter,
    NocturneExporter,
    PdfExporter,
    PlainTextExporter,
    _EXPORTERS,
    detect_unsupported_elements,
    escape_md,
    escape_ruby_markup,
    get_exporter,
    list_platforms,
    normalize_newlines,
    pagebreak_filter,
    process_content_for_platform,
    process_footnotes,
    process_image_placeholders,
    process_ruby_markup,
    ruby_filter,
    sanitize_for_kakuyomu,
    sanitize_for_markdown,
    sanitize_for_narou,
    sanitize_for_nocturne,
    sanitize_for_plain_text,
    sanitize_for_platform,
    wordcount_filter,
)

WARN_CONTENT = "<b>強調</b> 長い文章です"  # HTMLタグは非対応プラットフォームで警告になる
NOVEL = {"title": "星降る夜", "synopsis": "少女の物語", "is_adult": False}
CHAPTERS = [
    {"ep_num": 1, "title": "始まり", "content": "夕暮れの街を歩いた。"},
    {"ep_num": 2, "title": "続き", "content": "夜更けの海を見た。"},
]


class _Concrete(BaseExporter):
    platform = "concrete"
    description = "test"

    def export(self, novel, chapters):
        return "".join(self.export_stream(novel, chapters))

    def export_stream(self, novel, chapters):
        yield self._header(novel)
        for ch in chapters:
            yield self._format_chapter(ch)
        yield self._footer(novel)


class TestTextFilters:
    def test_normalize_newlines(self):
        assert normalize_newlines("a\r\nb\rc") == "a\nb\nc"

    def test_normalize_collapses_blank_lines(self):
        assert normalize_newlines("a\n\n\n\n\nb") == "a\n\nb"

    def test_normalize_empty(self):
        assert normalize_newlines("") == ""
        assert normalize_newlines(None) == ""

    def test_escape_ruby_markup_passthrough(self):
        assert escape_ruby_markup("|漢字《かんじ》|") == "|漢字《かんじ》|"

    def test_wordcount(self):
        assert wordcount_filter("あいう") == 3
        assert wordcount_filter("") == 0

    def test_ruby_filter_passthrough(self):
        assert ruby_filter("|漢字《かんじ》|") == "|漢字《かんじ》|"

    def test_escape_md(self):
        assert escape_md("a*b_c[d]") == "a\\*b\\_c\\[d\\]"
        assert escape_md("") == ""

    def test_escape_md_covers_all_chars(self):
        for ch in "\\`*_{}[]()#+-.!":
            assert ch + "\\" in escape_md(ch) or escape_md(ch).endswith("\\" + ch[0])

    @pytest.mark.parametrize(
        "platform,expected",
        [
            ("narou", "\n=====\n"),
            ("kakuyomu", "---\n"),
            ("nocturn", "\n---\n"),
            ("markdown", "---\n"),
            ("txt", "\n" + "-" * 20 + "\n"),
            ("other", "\n" + "-" * 20 + "\n"),
        ],
    )
    def test_pagebreak_filter(self, platform, expected):
        assert pagebreak_filter(platform) == expected

    def test_sanitize_for_platform_strips_control_chars(self):
        assert sanitize_for_platform("a\x00b\x1fc") == "abc"
        assert sanitize_for_platform(None) == ""


class TestProcessImagePlaceholders:
    def test_empty(self):
        assert process_image_placeholders("", "narou") == ""

    @pytest.mark.parametrize("platform", ["narou", "nocturn", "txt", "unknown"])
    def test_alt_text_converted(self, platform):
        out = process_image_placeholders("![猫](a.png) の絵", platform)
        assert out == "[画像: 猫] の絵"

    def test_no_alt_text(self):
        assert process_image_placeholders("![](a.png)", "narou") == "[画像]"

    def test_markdown_preserved(self):
        md = '![猫](a.png "title")'
        assert process_image_placeholders(md, "markdown") == md
        assert process_image_placeholders(md, "kakuyomu") == md

    def test_plain_text_platform(self):
        assert process_image_placeholders("![犬](b.png)", "txt") == "[画像: 犬]"


class TestProcessRubyMarkup:
    def test_empty(self):
        assert process_ruby_markup("", "narou") == ""

    @pytest.mark.parametrize("platform", ["narou", "kakuyomu", "nocturn"])
    def test_passthrough_platforms(self, platform):
        out = process_ruby_markup("|漢字《かんじ》|", platform)
        assert out == "|漢字《かんじ》|"

    def test_markdown_converts_to_html(self):
        assert process_ruby_markup("|漢字《かんじ》|", "markdown") == (
            "<ruby>漢字<rt>かんじ</rt></ruby>"
        )

    def test_txt_drops_markup(self):
        assert process_ruby_markup("|漢字《かんじ》|", "txt") == "漢字"

    def test_unknown_platform_drops_markup(self):
        assert process_ruby_markup("|漢字《かんじ》|", "zzz") == "漢字"


class TestProcessFootnotes:
    def test_empty(self):
        assert process_footnotes("", "narou") == ""

    @pytest.mark.parametrize("platform", ["narou", "nocturn", "txt", "zzz"])
    def test_bracket_platforms(self, platform):
        assert process_footnotes("^[注1]", platform) == "（注1）"

    @pytest.mark.parametrize("platform", ["kakuyomu", "markdown"])
    def test_markdown_platforms(self, platform):
        assert process_footnotes("^[注1]", platform) == "[^注1]"


class TestDetectUnsupportedElements:
    def test_empty(self):
        assert detect_unsupported_elements("", "narou") == []

    def test_image_warning(self):
        w = detect_unsupported_elements("![猫](a.png)", "narou")
        assert len(w) == 1
        assert "画像プレースホルダ" in w[0]

    def test_no_image_warning_for_markdown(self):
        assert detect_unsupported_elements("![猫](a.png)", "markdown") == []

    def test_footnote_warning(self):
        w = detect_unsupported_elements("^[注]", "txt")
        assert any("脚注" in x for x in w)

    def test_html_warning(self):
        w = detect_unsupported_elements("<b>x</b>", "narou")
        assert any("HTML" in x for x in w)

    def test_no_html_warning_for_markdown(self):
        assert detect_unsupported_elements("<b>x</b>", "markdown") == []


class TestProcessContentForPlatform:
    def test_narou_full(self):
        text = "![猫](a.png) |漢字《かんじ》| ^[注1]"
        out, warnings = process_content_for_platform(text, "narou")
        assert "[画像: 猫]" in out
        assert "|漢字《かんじ》|" in out
        assert "（注1）" in out
        assert len(warnings) >= 2

    def test_kakuyomu_full(self):
        text = "![猫](a.png) |漢字《かんじ》| ^[注1]"
        out, warnings = process_content_for_platform(text, "kakuyomu")
        assert "![猫](a.png)" in out
        assert "[^注1]" in out
        assert warnings == []

    def test_markdown_conversions(self):
        out, _ = process_content_for_platform("|漢字《かんじ》|", "markdown")
        assert "<ruby>" in out

    def test_txt_strips_bom(self):
        out, _ = process_content_for_platform("\ufeffhello", "txt")
        assert out == "hello"

    def test_newlines_normalised(self):
        out, _ = process_content_for_platform("a\r\n\r\n\r\n\r\nb", "narou")
        assert out == "a\n\nb"

    def test_image_warning_only_for_narou_family(self):
        _, w1 = process_content_for_platform("![猫](a.png)", "kakuyomu")
        assert not any("画像プレースホルダが検出されました" in x for x in w1)

    def test_footnote_conversion_no_warning_for_markdown(self):
        out, warnings = process_content_for_platform("^[注1]", "markdown")
        assert out == "[^注1]"
        assert warnings == []


class TestSanitizeHelpers:
    def test_sanitize_for_narou(self):
        out = sanitize_for_narou("![猫](a.png) |漢字《かんじ》|")
        assert "[画像: 猫]" in out
        assert "|漢字《かんじ》|" in out

    def test_sanitize_for_kakuyomu(self):
        assert "![猫](a.png)" in sanitize_for_kakuyomu("![猫](a.png)")

    def test_sanitize_for_nocturne(self):
        assert "[画像: 猫]" in sanitize_for_nocturne("![猫](a.png)")

    def test_sanitize_for_markdown(self):
        assert "<ruby>" in sanitize_for_markdown("|漢字《かんじ》|")

    def test_sanitize_for_plain_text(self):
        out = sanitize_for_plain_text("\ufeff![猫](a.png) |漢字《かんじ》|")
        assert not out.startswith("\ufeff")
        assert out == "[画像: 猫] 漢字"

    def test_sanitize_for_plain_text_strips_bom(self):
        # platform="txt" 経路でもBOMが除去されることを明示的に確認
        out, _ = process_content_for_platform("\ufeff本文", "txt")
        assert out == "本文"


class TestBaseExporter:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseExporter()

    def test_header_defaults(self):
        out = _Concrete()._header({})
        assert out == "# 無題\n\n\n"

    def test_header_with_values(self):
        assert _Concrete()._header(NOVEL) == "# 星降る夜\n\n少女の物語\n"

    def test_footer_default(self):
        assert _Concrete()._footer(NOVEL) == ""

    def test_format_chapter(self):
        out = _Concrete()._format_chapter({"ep_num": 3, "title": "T", "content": "B"})
        assert out == "## T\n\nB\n"

    def test_format_chapter_falls_back_to_ep_num(self):
        out = _Concrete()._format_chapter({"ep_num": 3})
        assert out == "## 第3話\n\n\n"

    def test_apply_template_filters_substitutions(self):
        e = _Concrete()
        out = e.apply_template_filters(
            "{{title}} / {{synopsis}} / {{is_adult}}", "narou", NOVEL
        )
        assert out == "星降る夜 / 少女の物語 / false"

    def test_apply_template_filters_chapter_vars(self):
        e = _Concrete()
        ch = {"ep_num": 7, "title": "CT", "content": "CC"}
        out = e.apply_template_filters(
            "{{chapter.title}}|{{chapter.content}}|{{chapter.number}}", "narou", NOVEL, ch
        )
        assert out == "CT|CC|7"

    def test_apply_template_filters_escape_md_filter(self):
        e = _Concrete()
        out = e.apply_template_filters("{{title|escape_md}}", "narou", NOVEL)
        assert "\\" in out or "*" not in out

    def test_apply_template_filters_ruby_filter(self):
        e = _Concrete()
        out = e.apply_template_filters("{{chapter.title|ruby}}", "narou", NOVEL, {"title": "漢字"})
        assert out == "漢字"

    def test_apply_template_filters_wordcount_filter(self):
        e = _Concrete()
        out = e.apply_template_filters("{{chapter.content|wordcount}}", "narou", NOVEL, {"content": "abcd"})
        assert out == "4"

    def test_apply_template_filters_pagebreak_filter(self):
        e = _Concrete()
        assert e.apply_template_filters("{{title|pagebreak}}", "narou", NOVEL) == "\n=====\n"

    def test_apply_template_filters_unknown_filter(self):
        e = _Concrete()
        assert e.apply_template_filters("{{title|weird}}", "narou", NOVEL) == "星降る夜"

    def test_apply_template_filters_unknown_var(self):
        e = _Concrete()
        assert e.apply_template_filters("{{nope|weird}}", "narou", NOVEL) == ""

    def test_apply_template_filters_dotted_unknown_var(self):
        e = _Concrete()
        assert e.apply_template_filters("{{other.x|weird}}", "narou", NOVEL, {"title": "T"}) == ""

    def test_apply_template_filters_dotted_without_chapter(self):
        e = _Concrete()
        assert e.apply_template_filters("{{chapter.title|weird}}", "narou", NOVEL) == ""

    def test_apply_template_filters_dotted_chapter_field(self):
        e = _Concrete()
        ch = {"title": "T", "content": "C", "ep_num": 1, "extra": "E"}
        out = e.apply_template_filters("{{chapter.extra|weird}}", "narou", NOVEL, ch)
        assert out == "E"

    def test_apply_template_filters_no_vars(self):
        e = _Concrete()
        assert e.apply_template_filters("static", "narou", NOVEL) == "static"


class TestNarouExporter:
    def test_class_attrs(self):
        assert NarouExporter.platform == "narou"
        assert NarouExporter.description

    def test_export(self):
        out = NarouExporter().export(NOVEL, CHAPTERS)
        assert "# 星降る夜" in out
        assert "## 始まり" in out
        assert "\n=====\n" in out
        assert out.count("\n=====\n") == 1

    def test_export_no_chapter_separator_when_single(self):
        out = NarouExporter().export(NOVEL, CHAPTERS[:1])
        assert "\n=====\n" not in out

    def test_export_warnings_on_first_chapter(self):
        chapters = [{"ep_num": 1, "title": "A", "content": "![猫](a.png) ^[注1] 長い文章です"}]
        out = NarouExporter().export(NOVEL, chapters)
        assert "<!-- WARNING:" in out
        assert "[画像: 猫]" in out
        assert "（注1）" in out

    def test_export_fallback_titles(self):
        chapters = [{"ep_num": 5, "content": "本文"}]
        out = NarouExporter().export(NOVEL, chapters)
        assert "## 第5話" in out

    def test_export_missing_content(self):
        out = NarouExporter().export(NOVEL, [{"ep_num": 1, "title": "T"}])
        assert "## T" in out

    def test_export_stream_is_generator(self):
        gen = NarouExporter().export_stream(NOVEL, CHAPTERS)
        assert next(gen).startswith("#")

    def test_export_uses_ruby_passthrough(self):
        chapters = [{"ep_num": 1, "title": "A", "content": "|漢字《かんじ》|"}]
        out = NarouExporter().export(NOVEL, chapters)
        assert "|漢字《かんじ》|" in out

    def test_footer_emitted_when_non_empty(self, monkeypatch):
        e = NarouExporter()
        monkeypatch.setattr(e, "_footer", lambda novel: "FOOTER")
        out = e.export(NOVEL, CHAPTERS[:1])
        assert "FOOTER" in out

    def test_empty_chapters(self):
        out = NarouExporter().export(NOVEL, [])
        assert out.startswith("# 星降る夜")


class TestKakuyomuExporter:
    def test_export(self):
        out = KakuyomuExporter().export(NOVEL, CHAPTERS)
        assert "# 星降る夜" in out
        assert "### 始まり" in out
        assert "---\n### 続き" in out

    def test_export_r18_tag(self):
        out = KakuyomuExporter().export({**NOVEL, "is_adult": True}, CHAPTERS[:1])
        assert out.rstrip().endswith("[R18]")

    def test_no_r18_tag(self):
        out = KakuyomuExporter().export(NOVEL, CHAPTERS[:1])
        assert "[R18]" not in out

    def test_warnings(self):
        chapters = [{"ep_num": 1, "title": "A", "content": WARN_CONTENT}]
        out = KakuyomuExporter().export(NOVEL, chapters)
        assert "<!-- WARNING:" in out

    def test_fallback_title(self):
        out = KakuyomuExporter().export(NOVEL, [{"ep_num": 9, "content": "x"}])
        assert "### 第9話" in out

    def test_defaults_when_no_metadata(self):
        out = KakuyomuExporter().export({}, [{"ep_num": 1, "content": "x"}])
        assert "# 無題" in out


class TestNocturneExporter:
    def test_export(self):
        out = NocturneExporter().export(NOVEL, CHAPTERS)
        assert "## 始まり" in out
        assert "[R18] 成年向けコンテンツを含みます。" in out
        assert "[年齢確認: 18歳以上であることを確認しました]" in out

    def test_r18_marker(self):
        out = NocturneExporter().export({**NOVEL, "is_adult": True}, CHAPTERS[:1])
        assert "[官能]" in out

    def test_no_sensory_marker(self):
        out = NocturneExporter().export(NOVEL, CHAPTERS[:1])
        assert "[官能]" not in out

    def test_chapter_separator(self):
        out = NocturneExporter().export(NOVEL, CHAPTERS)
        assert "\n---\n## 続き" in out

    def test_warnings(self):
        chapters = [{"ep_num": 1, "title": "A", "content": WARN_CONTENT}]
        assert "<!-- WARNING:" in NocturneExporter().export(NOVEL, chapters)

    def test_fallback_title(self):
        out = NocturneExporter().export(NOVEL, [{"ep_num": 4, "content": "x"}])
        assert "## 第4話" in out


class TestPlainTextExporter:
    def test_export(self):
        out = PlainTextExporter().export(NOVEL, CHAPTERS)
        assert "『星降る夜』" in out
        assert "◆ 始まり ◆" in out
        assert "=" * 30 in out
        assert ("-" * 20) in out

    def test_warnings(self):
        chapters = [{"ep_num": 1, "title": "A", "content": WARN_CONTENT}]
        assert "<!-- WARNING:" in PlainTextExporter().export(NOVEL, chapters)

    def test_fallback_title(self):
        out = PlainTextExporter().export(NOVEL, [{"ep_num": 2, "content": "x"}])
        assert "◆ 第2話 ◆" in out

    def test_defaults(self):
        out = PlainTextExporter().export({}, [])
        assert "『無題』" in out


class TestMarkdownExporter:
    def test_export_front_matter(self):
        novel = {**NOVEL, "tags": ["a", "b"]}
        out = MarkdownExporter().export(novel, CHAPTERS)
        assert out.startswith("---\n")
        assert 'title: "星降る夜"' in out
        assert 'description: "少女の物語"' in out
        assert "tags: [a, b]" in out

    def test_export_no_front_matter(self):
        out = MarkdownExporter().export({}, CHAPTERS)
        assert not out.startswith("---")
        assert "# 無題" in out

    def test_tags_as_string(self):
        out = MarkdownExporter().export({"title": "T", "tags": "x,y"}, [])
        assert "tags: [x,y]" in out

    def test_synopsis_escaped_in_front_matter(self):
        novel = {"title": "T", "synopsis": 'q"quote"\nsecond line'}
        out = MarkdownExporter().export(novel, [])
        assert 'description: "q\\"quote\\" second line"' in out

    def test_synopsis_blockquote(self):
        out = MarkdownExporter().export(NOVEL, [])
        assert "> 少女の物語" in out

    def test_chapter_separator(self):
        out = MarkdownExporter().export(NOVEL, CHAPTERS)
        assert "---\n## 続き" in out

    def test_markdown_supports_all_markup_so_no_warnings(self):
        # markdown は HTMLタグ/画像/脚注のいずれもサポート対象のため警告しない
        chapters = [{"ep_num": 1, "title": "A", "content": WARN_CONTENT}]
        assert "<!-- WARNING:" not in MarkdownExporter().export(NOVEL, chapters)

    def test_fallback_title(self):
        out = MarkdownExporter().export(NOVEL, [{"ep_num": 6, "content": "x"}])
        assert "## 第6話" in out


class TestEpubPdfExporters:
    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_platform(self, cls):
        assert cls.platform in ("epub", "pdf")
        assert cls.description

    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_export_with_front_matter(self, cls):
        novel = {**NOVEL, "tags": ["x"]}
        out = cls().export(novel, CHAPTERS)
        assert 'title: "星降る夜"' in out
        assert "tags: [x]" in out
        assert "## 始まり" in out
        assert "---\n## 続き" in out

    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_export_without_metadata(self, cls):
        out = cls().export({}, [{"ep_num": 1, "content": "x"}])
        assert not out.startswith("---")
        assert "## 第1話" in out

    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_tags_string(self, cls):
        assert "tags: [p, q]" in cls().export({"title": "T", "tags": "p, q"}, [])

    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_synopsis_escaped(self, cls):
        out = cls().export({"title": "T", "synopsis": 'q"\nw'}, [])
        assert 'q\\" w' in out

    @pytest.mark.parametrize("cls", [EpubExporter, PdfExporter])
    def test_warnings(self, cls):
        chapters = [{"ep_num": 1, "title": "A", "content": WARN_CONTENT}]
        assert "<!-- WARNING:" in cls().export(NOVEL, chapters)


class TestWarningInjection:
    """警告コメント出力は process_content_for_platform の返値に依存するため、
    実際の警告を発生させて各エクスポータの出力経路を検証する。"""

    @pytest.mark.parametrize(
        "cls", [NarouExporter, KakuyomuExporter, NocturneExporter, PlainTextExporter,
                MarkdownExporter, EpubExporter, PdfExporter]
    )
    def test_warning_comment_emitted_for_first_chapter_only(self, cls, monkeypatch):
        calls = {"n": 0}

        def _fake(text, platform):
            calls["n"] += 1
            return (text, [f"W{calls['n']}"])

        monkeypatch.setattr(
            "src.services.exporters.base.process_content_for_platform", _fake
        )
        out = cls().export(NOVEL, CHAPTERS)
        assert out.count("<!-- WARNING: W1 -->") == 1
        assert "W2" not in out

    @pytest.mark.parametrize(
        "cls", [NarouExporter, KakuyomuExporter, NocturneExporter, PlainTextExporter,
                MarkdownExporter, EpubExporter, PdfExporter]
    )
    def test_no_warning_comment_without_warnings(self, cls, monkeypatch):
        monkeypatch.setattr(
            "src.services.exporters.base.process_content_for_platform",
            lambda text, platform: (text, []),
        )
        assert "<!-- WARNING:" not in cls().export(NOVEL, CHAPTERS)

    def test_narou_footer_with_warning(self, monkeypatch):
        monkeypatch.setattr(
            "src.services.exporters.base.process_content_for_platform",
            lambda text, platform: (text, ["F"]),
        )
        e = NarouExporter()
        monkeypatch.setattr(e, "_footer", lambda novel: "FOOTER")
        out = e.export(NOVEL, CHAPTERS)
        assert out.count("<!-- WARNING: F -->") == 1
        assert out.rstrip().endswith("FOOTER")


class TestRegistry:
    def test_get_exporter_known(self):
        for platform in ("narou", "kakuyomu", "nocturn", "txt", "markdown", "epub", "pdf"):
            assert isinstance(get_exporter(platform), BaseExporter)

    def test_get_exporter_alias(self):
        assert isinstance(get_exporter("nocturne"), NocturneExporter)

    def test_get_exporter_unknown_defaults_to_narou(self):
        assert isinstance(get_exporter("bogus"), NarouExporter)

    def test_registry_keys(self):
        assert set(_EXPORTERS) == {
            "narou",
            "kakuyomu",
            "nocturn",
            "nocturne",
            "txt",
            "markdown",
            "epub",
            "pdf",
        }

    def test_list_platforms(self):
        rows = list_platforms()
        assert len(rows) == len(_EXPORTERS)
        assert all("platform" in r and "description" in r for r in rows)

    def test_get_exporter_returns_new_instance(self):
        assert get_exporter("narou") is not get_exporter("narou")

