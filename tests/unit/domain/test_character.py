"""src/domain/character.py (CharacterBase / CharacterCreate / Character) の単体テスト."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.character import Character, CharacterBase, CharacterCreate


class TestCharacterBase:
    """CharacterBase のテスト."""

    def test_create_valid(self):
        """全フィールド指定でキャラクター基底モデルを作成できる."""
        character = CharacterBase(
            character_id=1,
            name="テストキャラ",
            role="protagonist",
            traits=["勇敢", "親切"],
            background="背景設定",
            relationships={"hero": "友人"},
        )
        assert character.character_id == 1
        assert character.name == "テストキャラ"
        assert character.role == "protagonist"
        assert character.traits == ["勇敢", "親切"]
        assert character.background == "背景設定"
        assert character.relationships == {"hero": "友人"}

    def test_character_id_must_be_ge_1(self):
        """character_id は 1 以上でなければならない."""
        with pytest.raises(ValidationError):
            CharacterBase(character_id=0, name="x", role="y")

    def test_name_min_length(self):
        """name は最低 1 文字でなければならない."""
        with pytest.raises(ValidationError):
            CharacterBase(character_id=1, name="", role="y")

    def test_name_max_length(self):
        """name は 100 文字まででなければならない."""
        with pytest.raises(ValidationError):
            CharacterBase(character_id=1, name="x" * 101, role="y")

    def test_role_max_length(self):
        """role は 50 文字まででなければならない."""
        with pytest.raises(ValidationError):
            CharacterBase(character_id=1, name="x", role="z" * 51)

    def test_defaults(self):
        """省略フィールドはデフォルト値を持つ."""
        character = CharacterBase(character_id=1, name="x", role="y")
        assert character.traits == []
        assert character.background is None
        assert character.relationships == {}


class TestCharacterCreate:
    """CharacterCreate のテスト."""

    def test_create_valid(self):
        """name と role でキャラクター作成リクエストを作成できる."""
        req = CharacterCreate(name="テストキャラ", role="protagonist")
        assert req.name == "テストキャラ"
        assert req.role == "protagonist"

    def test_traits_optional_none(self):
        """traits は None を許容する."""
        req = CharacterCreate(name="x", role="y", traits=None)
        assert req.traits is None


class TestCharacter:
    """Character エンティティのテスト."""

    def test_create_valid(self):
        """完全なキャラクターエンティティを作成できる."""
        character = Character(
            character_id=1,
            name="テストキャラ",
            role="protagonist",
            current_emotion="joy",
            tension_contribution=0.3,
            emotional_resonance=0.7,
            book_id=1,
        )
        assert character.character_id == 1
        assert character.name == "テストキャラ"
        assert character.current_emotion == "joy"
        assert character.tension_contribution == 0.3
        assert character.emotional_resonance == 0.7
        assert character.book_id == 1

    def test_tension_contribution_out_of_range(self):
        """tension_contribution の範囲外値は ValidationError."""
        with pytest.raises(ValidationError):
            Character(character_id=1, name="x", role="y", tension_contribution=1.5)

    def test_emotional_resonance_out_of_range(self):
        """emotional_resonance の範囲外値は ValidationError."""
        with pytest.raises(ValidationError):
            Character(character_id=1, name="x", role="y", emotional_resonance=-0.1)

    def test_extra_field_forbidden(self):
        """extra=\"forbid\" により未定義フィールドは拒否される."""
        with pytest.raises(ValidationError):
            Character(character_id=1, name="x", role="y", unknown_field="value")
