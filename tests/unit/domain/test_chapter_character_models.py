"""Unit tests for pure pydantic domain models: chapter & character."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.chapter import ChapterBase, ChapterCreate
from src.domain.character import Character, CharacterBase, CharacterCreate


class TestChapterBase:
    def test_valid_construction(self):
        c = ChapterBase(ep_num=1, title="Title", content="body", word_count=4)
        assert c.ep_num == 1
        assert c.status == "draft"
        assert c.word_count == 4

    def test_invalid_ep_num(self):
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=0, title="T")

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ChapterBase(ep_num=1, title="T", status="bogus")

    def test_created_at_defaults_to_timestamp(self):
        c = ChapterBase(ep_num=1, title="T")
        assert c.created_at > 0


class TestChapterCreate:
    def test_title_required_and_max(self):
        c = ChapterCreate(title="ok", content="x")
        assert c.title == "ok"
        with pytest.raises(ValidationError):
            ChapterCreate(title="", content="x")


class TestCharacterBase:
    def test_valid_construction(self):
        ch = CharacterBase(character_id=1, name="Alice", role="protagonist")
        assert ch.character_id == 1
        assert ch.traits == []
        assert ch.relationships == {}

    def test_invalid_character_id(self):
        with pytest.raises(ValidationError):
            CharacterBase(character_id=0, name="A", role="r")

    def test_background_max_length(self):
        with pytest.raises(ValidationError):
            CharacterBase(character_id=1, name="A", role="r", background="x" * 2001)


class TestCharacterCreate:
    def test_minimum_fields(self):
        c = CharacterCreate(name="Bob", role="supporting")
        assert c.name == "Bob"


class TestCharacterEntity:
    def test_defaults(self):
        ch = Character(character_id=1, name="A", role="r")
        assert ch.current_emotion is None
        assert ch.tension_contribution == 0.0
        assert ch.book_id == 0

    def test_role_max_length(self):
        with pytest.raises(ValidationError):
            Character(character_id=1, name="A", role="x" * 51)
