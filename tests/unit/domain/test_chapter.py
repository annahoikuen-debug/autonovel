"""src/domain/chapter.py (ChapterBase / ChapterCreate / Chapter) の単体テスト."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.chapter import Chapter, ChapterBase, ChapterCreate
from src.domain.character import Character  # noqa: F401  forward reference 解決用

# Chapter の先方参照（list["Character"]）を解決する
Chapter.model_rebuild()


class TestChapterBase:
    """ChapterBase のテスト."""

    def test_create_valid(self):
        """必須項目 ep_num と title でインスタンス化できる."""
        chapter = ChapterBase(ep_num=1, title="第1章")
        assert chapter.ep_num == 1
        assert chapter.title == "第1章"
        assert chapter.content == ""
        assert chapter.status == "draft"
        assert chapter.word_count == 0

    def test_ep_num_must_be_ge_1(self):
        """ep_num は 1 以上でなければならない."""
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=0, title="x")

    def test_title_min_length(self):
        """title は最低 1 文字でなければならない."""
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=1, title="")

    def test_title_max_length(self):
        """title は 200 文字まででなければならない."""
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=1, title="x" * 201)

    def test_status_pattern(self):
        """status は draft/writing/completed/archived のいずれかでなければならない."""
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=1, title="x", status="invalid_status")

    def test_valid_statuses(self):
        """4 つのステータス全てが受理される."""
        for status in ("draft", "writing", "completed", "archived"):
            chapter = ChapterBase(ep_num=1, title="x", status=status)
            assert chapter.status == status


class TestChapterCreate:
    """ChapterCreate のテスト."""

    def test_create_valid(self):
        """title と ep_num と content でリクエストを作成できる."""
        req = ChapterCreate(title="第1章", ep_num=1, content="本文")
        assert req.title == "第1章"
        assert req.ep_num == 1
        assert req.content == "本文"

    def test_ep_num_optional(self):
        """ep_num は省略可能で、その場合は None."""
        req = ChapterCreate(title="第1章")
        assert req.ep_num is None


class TestChapter:
    """Chapter エンティティのテスト."""

    def test_create_valid(self):
        """完全な章エンティティを作成できる."""
        chapter = Chapter(
            id=1,
            ep_num=1,
            title="第1章",
            book_id=1,
            characters=[],
            tension=0.5,
            emotional_resonance=0.5,
        )
        assert chapter.id == 1
        assert chapter.ep_num == 1
        assert chapter.title == "第1章"
        assert chapter.book_id == 1
        assert chapter.is_completed is False

    def test_is_completed_true(self):
        """status == completed のとき is_completed は True."""
        chapter = Chapter(id=1, ep_num=1, title="x", status="completed")
        assert chapter.is_completed is True

    def test_tension_clamped(self):
        """tension は 0.0..1.0 の範囲で受理される."""
        chapter = Chapter(id=1, ep_num=1, title="x", tension=1.0)
        assert chapter.tension == 1.0

    def test_tension_out_of_range(self):
        """tension の範囲外値は ValidationError."""
        with pytest.raises(ValidationError):
            Chapter(id=1, ep_num=1, title="x", tension=1.5)

    def test_emotional_resonance_out_of_range(self):
        """emotional_resonance の範囲外値は ValidationError."""
        with pytest.raises(ValidationError):
            Chapter(id=1, ep_num=1, title="x", emotional_resonance=-0.1)

    def test_extra_field_forbidden(self):
        """extra=\"forbid\" により未定義フィールドは拒否される."""
        with pytest.raises(ValidationError):
            Chapter(id=1, ep_num=1, title="x", unknown_field="value")
