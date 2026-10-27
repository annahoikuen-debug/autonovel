"""Unit tests for src/services/exporters/epub_manifest_builder.py."""
import pytest

from src.services.exporters.epub_manifest_builder import (
    EpubIllustrationItem,
    EpubManifestBuilder,
    detect_image_media_type,
)

CHAPTERS = [
    {"title": "第一章", "href": "xhtml/p-001.xhtml"},
    {"title": "第二章", "href": "xhtml/p-002.xhtml"},
]


class TestDetectImageMediaType:
    def test_jpeg_magic(self):
        assert detect_image_media_type(data=b"\xff\xd8\xff\xe0rest") == "image/jpeg"

    def test_png_magic(self):
        assert detect_image_media_type(data=b"\x89PNG\r\n\x1a\nrest") == "image/png"

    def test_gif87_magic(self):
        assert detect_image_media_type(data=b"GIF87a....") == "image/gif"

    def test_gif89_magic(self):
        assert detect_image_media_type(data=b"GIF89a....") == "image/gif"

    def test_webp_magic(self):
        assert detect_image_media_type(data=b"RIFF1234WEBPVP8 ") == "image/webp"

    def test_riff_without_webp_falls_back_to_extension(self):
        assert detect_image_media_type("a.png", b"RIFF1234AVI ") == "image/png"

    def test_svg_magic(self):
        assert detect_image_media_type(data=b'<SVG xmlns="..."></svg>') == "image/svg+xml"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("a.JPG", "image/jpeg"),
            ("a.jpeg", "image/jpeg"),
            ("a.png", "image/png"),
            ("a.webp", "image/webp"),
            ("a.gif", "image/gif"),
            ("a.svg", "image/svg+xml"),
        ],
    )
    def test_extension_fallback(self, name, expected):
        assert detect_image_media_type(name) == expected

    def test_no_extension_defaults_jpeg(self):
        assert detect_image_media_type("cover") == "image/jpeg"

    def test_unknown_extension_defaults_jpeg(self):
        assert detect_image_media_type("a.bmp") == "image/jpeg"

    def test_unknown_bytes_and_no_extension(self):
        assert detect_image_media_type("", b"\x00\x01") == "image/jpeg"


class TestEpubIllustrationItem:
    def test_auto_detect_from_bytes(self):
        item = EpubIllustrationItem(
            image_id="i1", image_bytes=b"\x89PNG\r\n\x1a\n", file_name="x.bin"
        )
        assert item.media_type == "image/png"

    def test_explicit_media_type_kept(self):
        item = EpubIllustrationItem(
            image_id="i1",
            image_bytes=b"\x89PNG\r\n\x1a\n",
            file_name="x.bin",
            media_type="application/octet-stream",
        )
        assert item.media_type == "application/octet-stream"

    def test_empty_media_type_replaced(self):
        item = EpubIllustrationItem(image_id="i1", image_bytes=b"", file_name="a.png", media_type="")
        assert item.media_type == "image/png"

    def test_defaults(self):
        item = EpubIllustrationItem(image_id="i1", image_bytes=b"", file_name="a.png")
        assert item.position == "chapter_start"
        assert item.chapter_index is None
        assert item.caption == ""


class TestBuildNavXhtml:
    def test_basic(self):
        out = EpubManifestBuilder.build_nav_xhtml("目次", CHAPTERS)
        assert 'epub:type="toc"' in out
        assert '<a href="xhtml/p-001.xhtml">第一章</a>' in out
        assert '<a href="xhtml/p-002.xhtml">第二章</a>' in out
        assert "<title>目次</title>" in out

    def test_default_href_and_title(self):
        out = EpubManifestBuilder.build_nav_xhtml("目次", [{}])
        assert "xhtml/p-001.xhtml" in out
        assert "第1話" in out

    def test_escapes_title(self):
        out = EpubManifestBuilder.build_nav_xhtml("目次", [{"title": "A & B"}])
        assert "A &amp; B" in out

    def test_exclude_hrefs(self):
        out = EpubManifestBuilder.build_nav_xhtml(
            "目次", CHAPTERS, exclude_hrefs={"xhtml/p-001.xhtml"}
        )
        assert "p-001.xhtml" not in out
        assert "p-002.xhtml" in out

    def test_custom_css(self):
        out = EpubManifestBuilder.build_nav_xhtml("目次", [], css_rel_path="a/b.css")
        assert 'href="a/b.css"' in out

    def test_empty_chapters(self):
        out = EpubManifestBuilder.build_nav_xhtml("目次", [])
        assert "<ol>\n\n</ol>" in out


class TestBuildTocNcx:
    def test_basic(self):
        out = EpubManifestBuilder.build_toc_ncx("uuid-1", "タイトル", CHAPTERS)
        assert "urn:uuid:uuid-1" in out
        assert "<text>第一章</text>" in out
        assert '<content src="xhtml/p-001.xhtml"/>' in out
        assert 'playOrder="1"' in out
        assert 'playOrder="2"' in out

    def test_default_href_and_title(self):
        out = EpubManifestBuilder.build_toc_ncx("u", "T", [{}])
        assert "第1話" in out
        assert "xhtml/p-001.xhtml" in out

    def test_exclude_hrefs_renumbers(self):
        out = EpubManifestBuilder.build_toc_ncx(
            "u", "T", CHAPTERS, exclude_hrefs={"xhtml/p-001.xhtml"}
        )
        assert "p-001.xhtml" not in out
        assert 'playOrder="1"' in out
        assert 'playOrder="2"' not in out

    def test_escaped_title(self):
        out = EpubManifestBuilder.build_toc_ncx("u", "A & B", [])
        assert "<text>A &amp; B</text>" in out

    def test_depth_metadata(self):
        out = EpubManifestBuilder.build_toc_ncx("u", "T", [])
        assert 'name="dtb:depth"' in out
        assert 'version="2005-1"' in out


class TestBuildCoverXhtml:
    def test_defaults(self):
        out = EpubManifestBuilder.build_cover_xhtml()
        assert 'src="images/cover.jpg"' in out
        assert 'alt="表紙"' in out
        assert 'class="p-cover"' in out
        assert "<title>表紙</title>" in out

    def test_custom(self):
        out = EpubManifestBuilder.build_cover_xhtml("i/c.png", "a/b.css")
        assert 'src="i/c.png"' in out
        assert 'href="a/b.css"' in out


def _ill(**kw):
    base = dict(image_id="i1", image_bytes=b"\x89PNG\r\n\x1a\n", file_name="a.png")
    base.update(kw)
    return EpubIllustrationItem(**base)


class TestBuildStandardOpf:
    def test_minimal(self):
        out = EpubManifestBuilder.build_standard_opf("u1", "タイトル")
        assert "urn:uuid:u1" in out
        assert "<dc:title>タイトル</dc:title>" in out
        assert "<dc:creator>AI Novelist</dc:creator>" in out
        assert "<dc:publisher>AutoNovel</dc:publisher>" in out
        assert 'page-progression-direction="rtl"' in out
        assert "<dc:language>ja</dc:language>" in out

    def test_custom_metadata(self):
        out = EpubManifestBuilder.build_standard_opf("u", "T", author="著者", publisher="社")
        assert "<dc:creator>著者</dc:creator>" in out
        assert "<dc:publisher>社</dc:publisher>" in out

    def test_escapes_metadata(self):
        out = EpubManifestBuilder.build_standard_opf("u", "A & B", author="<x>")
        assert "<dc:title>A &amp; B</dc:title>" in out
        assert "&lt;x&gt;" in out

    def test_manifest_items(self):
        items = [{"id": "p-1", "href": "a.xhtml", "media-type": "application/xhtml+xml"}]
        out = EpubManifestBuilder.build_standard_opf("u", "T", manifest_items=items)
        assert '<item id="p-1" href="a.xhtml" media-type="application/xhtml+xml" />' in out

    def test_manifest_item_properties(self):
        items = [
            {
                "id": "cover-image",
                "href": "c.jpg",
                "media-type": "image/jpeg",
                "properties": "cover-image",
            }
        ]
        out = EpubManifestBuilder.build_standard_opf("u", "T", manifest_items=items, has_cover=True)
        assert 'properties="cover-image"' in out
        assert '<meta name="cover" content="cover-image" />' in out

    def test_no_cover_meta(self):
        out = EpubManifestBuilder.build_standard_opf("u", "T")
        assert '<meta name="cover"' not in out

    def test_spine_items(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u", "T", spine_items=["p-cover", "p-1", "p-2"]
        )
        assert '<itemref idref="p-cover" />' in out
        assert '<itemref idref="p-1" />' in out

    def test_illustration_manifest_entry(self):
        out = EpubManifestBuilder.build_standard_opf("u", "T", illustrations=[_ill()])
        assert '<item id="img-i1" href="images/a.png" media-type="image/png" />' in out

    def test_illustration_duplicate_id_skipped(self):
        items = [{"id": "img-i1", "href": "existing.png", "media-type": "image/png"}]
        out = EpubManifestBuilder.build_standard_opf(
            "u", "T", manifest_items=items, illustrations=[_ill()]
        )
        assert 'href="existing.png"' in out
        assert 'href="images/a.png"' not in out

    def test_chapter_start_inserted_before(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u",
            "T",
            spine_items=["p-1"],
            illustrations=[_ill(image_id="s1", position="chapter_start", chapter_index=1)],
        )
        assert out.index('idref="p-ill-s1"') < out.index('idref="p-1"')

    def test_chapter_end_inserted_after(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u",
            "T",
            spine_items=["p-1"],
            illustrations=[_ill(image_id="e1", position="chapter_end", chapter_index=1)],
        )
        assert out.index('idref="p-1"') < out.index('idref="p-ill-e1"')

    def test_multiple_illustrations_same_chapter(self):
        ills = [
            _ill(image_id="a", position="chapter_start", chapter_index=1),
            _ill(image_id="b", position="chapter_start", chapter_index=1),
        ]
        out = EpubManifestBuilder.build_standard_opf("u", "T", spine_items=["p-1"], illustrations=ills)
        assert out.index('idref="p-ill-a"') < out.index('idref="p-ill-b"')
        assert out.index('idref="p-ill-b"') < out.index('idref="p-1"')

    def test_chapter_index_not_in_spine_dropped(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u",
            "T",
            spine_items=["p-1"],
            illustrations=[_ill(image_id="x", position="chapter_start", chapter_index=9)],
        )
        assert 'idref="p-ill-x"' not in out

    def test_frontmatter_after_cover(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u",
            "T",
            spine_items=["p-cover", "p-1"],
            illustrations=[_ill(image_id="f1", position="frontmatter")],
        )
        assert out.index('idref="p-cover"') < out.index('idref="p-ill-f1"')
        assert out.index('idref="p-ill-f1"') < out.index('idref="p-1"')

    def test_frontmatter_without_cover_first(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u",
            "T",
            spine_items=["p-1"],
            illustrations=[_ill(image_id="f1", position="frontmatter")],
        )
        assert out.index('idref="p-ill-f1"') < out.index('idref="p-1"')

    def test_non_chapter_spine_refs_kept(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u", "T", spine_items=["nav", "ncx", "p-1"], illustrations=[]
        )
        assert '<itemref idref="nav" />' in out
        assert '<itemref idref="ncx" />' in out

    def test_unknown_illustration_position_ignored(self):
        out = EpubManifestBuilder.build_standard_opf(
            "u", "T", spine_items=["p-1"], illustrations=[_ill(position="middle")]
        )
        assert "<dc:title>T</dc:title>" in out
        assert 'idref="p-1"' in out
