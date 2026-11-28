"""src/domain/entities/character.py (Character / CharacterArc) の単体テスト."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities.character import Character, CharacterArc
from src.domain.value_objects.ids import CharacterId, NovelId


class TestCharacterCreate:
    """Character.create ファクトリメソッドのテスト."""

    def test_create_character(self):
        novel_id = NovelId.generate()
        character = Character.create(
            novel_id=novel_id,
            name="テストキャラ",
            role="protagonist",
            personality="勇敢",
            ability="剣術",
        )
        assert isinstance(character.id, CharacterId)
        assert character.novel_id == novel_id
        assert character.name == "テストキャラ"
        assert character.role == "protagonist"
        assert character.personality == "勇敢"
        assert character.ability == "剣術"
        assert character.registry_data == ""
        assert isinstance(character.created_at, datetime)
        assert isinstance(character.updated_at, datetime)
        assert character.created_at == character.updated_at
        assert character._arcs == []

    def test_create_character_defaults(self):
        novel_id = NovelId.generate()
        character = Character.create(
            novel_id=novel_id,
            name="キャラ",
            role="サブ",
        )
        assert character.personality == ""
        assert character.ability == ""


class TestCharacterUpdate:
    """Character.update_details のテスト."""

    def test_update_all_fields(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "元名", "元ロール")
        before = character.updated_at
        character.update_details(
            name="新名",
            role="新ロール",
            personality="新人格",
            ability="新能力",
            registry_data="新レジストリ",
        )
        assert character.name == "新名"
        assert character.role == "新ロール"
        assert character.personality == "新人格"
        assert character.ability == "新能力"
        assert character.registry_data == "新レジストリ"
        assert character.updated_at >= before

    def test_update_partial_fields(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "元名", "元ロール", "元人格")
        character.update_details(name="新名のみ")
        assert character.name == "新名のみ"
        assert character.role == "元ロール"
        assert character.personality == "元人格"

    def test_update_empty_name_raises(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "名", "ロール")
        with pytest.raises(ValueError, match="Character name cannot be empty"):
            character.update_details(name="   ")


class TestCharacterArc:
    """CharacterArc のテスト."""

    def test_add_arc_valid(self):
        novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        character = Character.create(novel_id, "キャラ", "ロール")
        arc = CharacterArc.create(
            novel_id=novel_id,
            character_id=character_id,
            arc_name="成長",
            stages=["stage1", "stage2", "stage3"],
        )
        # character_id が異なるのでエラー
        with pytest.raises(ValueError, match="Arc character_id must match this character"):
            character.add_arc(arc)

    def test_add_arc_matching_character(self):
        novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        character = Character.create(novel_id, "キャラ", "ロール")
        # id を character.id と一致させるため、作り直す
        arc = CharacterArc(
            id=character_id,
            novel_id=novel_id,
            character_id=character.id,
            arc_name="成長",
            arc_stages=["stage1", "stage2"],
        )
        character.add_arc(arc)
        arcs = character.get_arcs()
        assert len(arcs) == 1
        assert arcs[0] is arc

    def test_add_arc_wrong_novel_raises(self):
        novel_id = NovelId.generate()
        other_novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        character = Character.create(novel_id, "キャラ", "ロール")
        arc = CharacterArc(
            id=character_id,
            novel_id=other_novel_id,
            character_id=character.id,
            arc_name="成長",
            arc_stages=["s1"],
        )
        with pytest.raises(ValueError, match="Arc novel_id must match this character's novel"):
            character.add_arc(arc)

    def test_get_current_arc_none(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "キャラ", "ロール")
        assert character.get_current_arc() is None

    def test_get_current_arc_active(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "キャラ", "ロール")
        arc = CharacterArc.create(
            novel_id=novel_id,
            character_id=character.id,
            arc_name="進行中",
            stages=["s1", "s2"],
        )
        character.add_arc(arc)
        current = character.get_current_arc()
        assert current is arc

    def test_arc_advance_stage(self):
        novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        arc = CharacterArc.create(
            novel_id=novel_id,
            character_id=character_id,
            arc_name="アーク",
            stages=["s1", "s2", "s3"],
        )
        assert arc.current_stage_index == 0
        assert arc.get_current_stage() == "s1"
        assert arc.get_progress() == 1 / 3
        assert arc.advance_stage() is False
        assert arc.current_stage_index == 1
        assert arc.get_current_stage() == "s2"
        assert arc.advance_stage() is False
        assert arc.current_stage_index == 2
        assert arc.get_current_stage() == "s3"
        # 最後のステージで advance すると完了
        assert arc.advance_stage() is True
        assert arc.is_completed is True

    def test_arc_advance_stage_empty(self):
        novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        arc = CharacterArc.create(
            novel_id=novel_id,
            character_id=character_id,
            arc_name="空アーク",
            stages=[],
        )
        assert arc.get_progress() == 0.0
        assert arc.get_current_stage() is None

    def test_arc_empty_name_raises(self):
        novel_id = NovelId.generate()
        character_id = CharacterId.generate()
        with pytest.raises(ValueError, match="Arc name cannot be empty"):
            CharacterArc(
                id=character_id,
                novel_id=novel_id,
                character_id=character_id,
                arc_name="   ",
                arc_stages=["s1"],
            )

    def test_character_eq_same_id(self):
        novel_id = NovelId.generate()
        char_id = CharacterId.generate()
        c1 = Character(
            id=char_id,
            novel_id=novel_id,
            name="a",
            role="r",
        )
        c2 = Character(
            id=char_id,
            novel_id=novel_id,
            name="b",
            role="r",
        )
        assert c1 == c2
        assert hash(c1) == hash(c2)

    def test_character_eq_diff_id(self):
        novel_id = NovelId.generate()
        c1 = Character.create(novel_id, "a", "r")
        c2 = Character.create(novel_id, "a", "r")
        assert c1 != c2

    def test_to_metadata(self):
        novel_id = NovelId.generate()
        character = Character.create(novel_id, "名前", "役割", "人格", "能力")
        metadata = character.to_metadata()
        assert metadata.name == "名前"
        assert metadata.role == "役割"
        assert metadata.personality == "人格"
        assert metadata.ability == "能力"
