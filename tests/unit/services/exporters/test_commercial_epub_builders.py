"""Unit tests for the two commercial EPUB builders."""
import io
import zipfile

import pytest

from src.services.exporters.commercial_epub_builder import PureCommercialEpubBuilder
from src.services.exporters.epub_commercial_builder import CommercialEpubBuilder
from src.services.exporters.epub_manifest_builder import EpubIllustrationItem


def _entries(raw: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _opf(raw: bytes) -> str:
    return _entries(raw)["item/standard.opf"].decode("utf-8")


class TestPureCommercialEpubBuilder:
    def _build(self, **kw):
        chapters = kw.pop(
            "chapters", [{"title": "第1話", "body": "本文一行\n\n「セリフ」"}]
        )
        return PureCommercialEpubBuilder().build_epub(
            title=kw.pop("title", "星降る夜"),
            author=kw.pop("author", "著者"),
            chapters=chapters,
            **kw,
        )

    def test_mimetype_first_and_stored(self):
        raw = self._build()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.namelist()[0] == "mimetype"
            assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert zf.read("mimetype") == b"application/epub+zip"

    def test_container_and_css_present(self):
        e = _entries(self._build())
        assert b"OEBPS/content.opf" in e["META-INF/container.xml"]
        assert b"writing-mode: vertical-rl" in e["OEBPS/styles/vertical.css"]

    def test_middle_page(self):
        e = _entries(self._build())
        html = e["OEBPS/middle-page.xhtml"].decode()
        assert "<div class=\"title\">星降る夜</div>" in html
        assert "<div class=\"author\">著者</div>" in html

    def test_chapter_page(self):
        e = _entries(self._build())
        html = e["OEBPS/chapter_1.xhtml"].decode()
        assert "<h2>第1話</h2>" in html
        assert '<p class="dialogue">「セリフ」</p>' in html

    def test_chapter_default_title(self):
        e = _entries(self._build(chapters=[{"body": "本文"}]))
        assert "<h2>第1話</h2>" in e["OEBPS/chapter_1.xhtml"].decode()

    def test_opf_metadata(self):
        with zipfile.ZipFile(io.BytesIO(self._build())) as zf:
            opf = zf.read("OEBPS/content.opf").decode()
        assert "<dc:title>星降る夜</dc:title>" in opf
        assert "<dc:creator>著者</dc:creator>" in opf
        assert 'page-progression-direction="rtl"' in opf
        assert "<dc:language>ja</dc:language>" in opf
        assert '<itemref idref="middle-page"/>' in opf
        assert '<itemref idref="chapter_1"/>' in opf

    def test_no_cover_by_default(self):
        e = _entries(self._build())
        assert "OEBPS/cover.xhtml" not in e
        assert "OEBPS/images/cover.png" not in e
        with zipfile.ZipFile(io.BytesIO(self._build())) as zf:
            opf = zf.read("OEBPS/content.opf").decode()
        assert 'idref="cover"' not in opf

    def test_with_cover(self):
        raw = self._build(cover_image_bytes=b"\x89PNG\r\n\x1a\nDATA")
        e = _entries(raw)
        assert e["OEBPS/images/cover.png"] == b"\x89PNG\r\n\x1a\nDATA"
        cover = e["OEBPS/cover.xhtml"].decode()
        assert 'src="images/cover.png"' in cover
        assert "text-align: center" in cover
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            opf = zf.read("OEBPS/content.opf").decode()
        assert 'id="cover-image"' in opf
        assert 'id="cover"' in opf
        assert '<itemref idref="cover"/>' in opf

    def test_multiple_chapters(self):
        e = _entries(
            self._build(
                chapters=[{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]
            )
        )
        assert "OEBPS/chapter_1.xhtml" in e
        assert "OEBPS/chapter_2.xhtml" in e

    def test_no_chapters(self):
        raw = self._build(chapters=[])
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            opf = zf.read("OEBPS/content.opf").decode()
        assert "chapter_1" not in opf
        assert 'idref="middle-page"' in opf

    def test_uuid_is_random(self):
        import re

        with zipfile.ZipFile(io.BytesIO(self._build())) as zf1:
            a = zf1.read("OEBPS/content.opf").decode()
        with zipfile.ZipFile(io.BytesIO(self._build())) as zf2:
            b = zf2.read("OEBPS/content.opf").decode()
        ua = re.search(r"urn:uuid:([0-9a-f-]+)", a).group(1)
        ub = re.search(r"urn:uuid:([0-9a-f-]+)", b).group(1)
        assert ua != ub


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


class TestCommercialEpubBuilder:
    def _build(self, meta=None, chapters=None, images=None):
        return CommercialEpubBuilder().build_commercial_epub(
            meta if meta is not None else {"uuid": "u-1", "title": "T", "author": "A"},
            chapters
            if chapters is not None
            else [{"title": "第1話", "content": "本文"}, {"title": "第2話", "content": "本文2"}],
            images,
        )

    def test_mimetype_first(self):
        raw = self._build()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert zf.namelist()[0] == "mimetype"
            assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED

    def test_static_entries(self):
        e = _entries(self._build())
        assert b"item/standard.opf" in e["META-INF/container.xml"]
        assert b"writing-mode: vertical-rl" in e["item/style/vertical.css"]
        assert "epub:type=\"toc\"" in e["item/nav.xhtml"].decode()
        assert "urn:uuid:u-1" in e["item/toc.ncx"].decode()

    def test_chapter_files(self):
        e = _entries(self._build())
        assert "item/xhtml/p-001.xhtml" in e
        assert "item/xhtml/p-002.xhtml" in e
        assert "<h1>第1話</h1>" in e["item/xhtml/p-001.xhtml"].decode()

    def test_chapter_defaults(self):
        e = _entries(self._build(chapters=[{}, {"title": None, "content": None}]))
        assert "<h1>第1話</h1>" in e["item/xhtml/p-001.xhtml"].decode()
        assert "<h1>第2話</h1>" in e["item/xhtml/p-002.xhtml"].decode()

    def test_opf_manifest_and_spine(self):
        opf = _opf(self._build())
        assert 'id="style"' in opf
        assert 'id="nav"' in opf
        assert 'id="ncx"' in opf
        assert 'id="p-001"' in opf
        assert 'idref="p-002"' in opf
        assert "<dc:title>T</dc:title>" in opf
        assert "<dc:creator>A</dc:creator>" in opf
        assert "<dc:publisher>AutoNovel</dc:publisher>" in opf

    def test_metadata_defaults(self):
        opf = _opf(self._build(meta={}))
        assert "<dc:title>無題</dc:title>" in opf
        assert "<dc:creator>AI Novelist</dc:creator>" in opf
        assert "<dc:publisher>AutoNovel</dc:publisher>" in opf

    def test_uuid_generated_when_missing(self):
        import re

        opf = _opf(self._build(meta={"title": "T"}))
        uuid_val = re.search(r"urn:uuid:([0-9a-f-]{36})", opf).group(1)
        assert uuid_val

    def test_no_cover(self):
        e = _entries(self._build())
        assert "item/xhtml/cover.xhtml" not in e
        assert 'id="cover-image"' not in _opf(self._build())

    def test_with_cover(self):
        e = _entries(self._build(meta={"title": "T", "cover_image_bytes": b"JPEGDATA"}))
        assert e["item/images/cover.jpg"] == b"JPEGDATA"
        assert "item/xhtml/cover.xhtml" in e
        opf = _opf(self._build(meta={"title": "T", "cover_image_bytes": b"JPEGDATA"}))
        assert 'properties="cover-image"' in opf
        assert 'idref="p-cover"' in opf
        assert '<meta name="cover" content="cover-image" />' in opf

    def test_illustration_dicts(self):
        images = [
            {
                "image_id": "i1",
                "image_bytes": PNG,
                "file_name": "a.png",
                "media_type": "image/png",
                "position": "chapter_start",
                "chapter_index": 1,
                "caption": "キャプ",
            }
        ]
        e = _entries(self._build(images=images))
        assert e["item/images/a.png"] == PNG
        ill = e["item/xhtml/ill-i1.xhtml"].decode()
        assert 'src="../images/a.png"' in ill
        assert "キャプ" in ill
        opf = _opf(self._build(images=images))
        assert 'id="img-i1"' in opf
        assert 'id="p-ill-i1"' in opf
        assert opf.index('idref="p-ill-i1"') < opf.index('idref="p-001"')

    def test_illustration_dict_defaults(self):
        images = [{"image_bytes": PNG}]
        e = _entries(self._build(images=images))
        assert "item/images/illustration_1.jpg" in e
        assert "item/xhtml/ill-ill-1.xhtml" in e

    def test_illustration_epub_item_instance(self):
        item = EpubIllustrationItem(
            image_id="obj1", image_bytes=PNG, file_name="o.png", media_type="image/png"
        )
        e = _entries(self._build(images=[item]))
        assert "item/images/o.png" in e
        assert "item/xhtml/ill-obj1.xhtml" in e

    def test_illustration_unsupported_type_skipped(self):
        e = _entries(self._build(images=["not-an-image", 42, None]))
        assert not any(n.startswith("item/xhtml/ill-") for n in e)

    def test_illustration_empty_bytes_skipped(self):
        e = _entries(self._build(images=[{"image_id": "e1", "image_bytes": b"", "file_name": "e.png"}]))
        assert not any(n.startswith("item/xhtml/ill-") for n in e)

    def test_duplicate_ids_deduplicated(self):
        images = [
            {"image_id": "dup", "image_bytes": PNG, "file_name": "a.png"},
            {"image_id": "dup", "image_bytes": PNG, "file_name": "a.png"},
        ]
        e = _entries(self._build(images=images))
        assert "item/images/a.png" in e
        assert "item/images/a_1.png" in e
        assert "item/xhtml/ill-dup.xhtml" in e
        assert "item/xhtml/ill-dup_1.xhtml" in e

    def test_duplicate_filename_without_extension(self):
        images = [
            {"image_id": "a", "image_bytes": PNG, "file_name": "noext"},
            {"image_id": "b", "image_bytes": PNG, "file_name": "noext"},
        ]
        e = _entries(self._build(images=images))
        assert "item/images/noext" in e
        assert "item/images/noext_1.jpg" in e

    def test_illustration_caption_default_title(self):
        images = [{"image_id": "c1", "image_bytes": PNG, "file_name": "c.png"}]
        e = _entries(self._build(images=images))
        assert "<title>挿絵</title>" in e["item/xhtml/ill-c1.xhtml"].decode()

    def test_illustration_page_end_position(self):
        images = [
            {
                "image_id": "e1",
                "image_bytes": PNG,
                "file_name": "e.png",
                "position": "chapter_end",
                "chapter_index": 1,
            }
        ]
        opf = _opf(self._build(images=images))
        assert opf.index('idref="p-001"') < opf.index('idref="p-ill-e1"')

    def test_illustration_frontmatter(self):
        images = [
            {
                "image_id": "f1",
                "image_bytes": PNG,
                "file_name": "f.png",
                "position": "frontmatter",
            }
        ]
        opf = _opf(self._build(meta={"title": "T", "cover_image_bytes": b"J"}, images=images))
        assert opf.index('idref="p-cover"') < opf.index('idref="p-ill-f1"')
        assert opf.index('idref="p-ill-f1"') < opf.index('idref="p-001"')

    def test_no_chapters(self):
        e = _entries(self._build(chapters=[]))
        assert "item/xhtml/p-001.xhtml" not in e
        assert "<ol>" in e["item/nav.xhtml"].decode()

    def test_illustration_excluded_from_nav(self):
        images = [{"image_id": "n1", "image_bytes": PNG, "file_name": "n.png"}]
        e = _entries(self._build(images=images))
        assert "ill-n1" not in e["item/nav.xhtml"].decode()
        assert "ill-n1" not in e["item/toc.ncx"].decode()
