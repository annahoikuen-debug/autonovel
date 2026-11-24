"""src/domain/entities/novel.py (Novel / Chapter / Episode / Volume) の単体テスト."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities.novel import Chapter, Episode, Novel, Volume
from src.domain.value_objects.ids import NovelId, UserId
from src.domain.value_objects.metadata import NovelMode, NovelStatus
from src.domain.value_objects.scores import CostScore
from src.domain.value_objects.text import Catchcopy, Genre, Summary, Title


class TestNovelCreate:
    """Novel.create ファクトリメソッドのテスト."""

    def test_create_novel(self):
        author_id = UserId.generate()
        novel = Novel.create(
            title="テスト小説",
            author_id=author_id,
            genre="fantasy",
            catchcopy="キャッチ",
            synopsis="あらすじ",
            concept="コンセプト",
            target_episodes=10,
        )
        assert isinstance(novel.id, NovelId)
        assert novel.title == Title("テスト小説")
        assert novel.author_id == author_id
        assert novel.genre == Genre("fantasy")
        assert novel.catchcopy == Catchcopy("キャッチ")
        assert novel.synopsis == Summary("あらすじ")
        assert novel.concept == Summary("コンセプト")
        assert novel.status == NovelStatus.DRAFT
        assert novel.mode == NovelMode.EASY
        assert novel.target_episodes == 10
        assert isinstance(novel.created_at, datetime)
        assert isinstance(novel.updated_at, datetime)
        assert novel.created_at == novel.updated_at
        assert novel.cumulative_tension == 0
        assert novel.cumulative_qol == 0
        assert isinstance(novel.cumulative_cost, CostScore)
        assert novel.cumulative_cost.value == 0.0
        assert novel.sanctuary_integrity == 100
        assert novel.current_branch_id is None

    def test_create_novel_defaults(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        assert novel.title == Title("t")
        assert novel.genre == Genre("")
        assert novel.target_episodes == 50
        assert novel.mode == NovelMode.EASY


class TestNovelMethods:
    """Novel のメソッドテスト."""

    def test_update_metadata(self):
        author_id = UserId.generate()
        novel = Novel.create(title="元タイトル", author_id=author_id)
        before = novel.updated_at
        novel.update_metadata(
            title="新タイトル",
            genre="sf",
            catchcopy="新キャッチ",
            synopsis="新あらすじ",
            concept="新コンセプト",
            target_episodes=20,
            style_dna="dna",
        )
        assert novel.title == Title("新タイトル")
        assert novel.genre == Genre("sf")
        assert novel.catchcopy == Catchcopy("新キャッチ")
        assert novel.synopsis == Summary("新あらすじ")
        assert novel.concept == Summary("新コンセプト")
        assert novel.target_episodes == 20
        assert novel.style_dna == "dna"
        assert novel.updated_at >= before

    def test_update_metadata_target_episodes_zero_raises(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        with pytest.raises(ValueError, match="Target episodes must be at least 1"):
            novel.update_metadata(target_episodes=0)

    def test_change_status(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        assert novel.status == NovelStatus.DRAFT
        novel.change_status(NovelStatus.DRAFT)
        assert novel.status == NovelStatus.DRAFT

    def test_set_mode(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        novel.set_mode(NovelMode.EASY)
        assert novel.mode == NovelMode.EASY

    def test_set_current_branch(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        branch_id = NovelId.generate()
        novel.set_current_branch(branch_id)
        assert novel.current_branch_id == branch_id

    def test_add_tension(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        novel.add_tension(10)
        assert novel.cumulative_tension == 10
        novel.add_tension(-3)
        assert novel.cumulative_tension == 7

    def test_add_qol(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        novel.add_qol(5)
        assert novel.cumulative_qol == 5

    def test_add_cost(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        novel.add_cost(1.5, tokens=1000)
        assert novel.cumulative_cost.value == 1.5
        assert novel.cumulative_cost.tokens_used == 1000
        novel.add_cost(0.5, tokens=500)
        assert novel.cumulative_cost.value == 2.0
        assert novel.cumulative_cost.tokens_used == 1500

    def test_update_sanctuary_integrity(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        novel.update_sanctuary_integrity(50)
        assert novel.sanctuary_integrity == 50

    def test_update_sanctuary_integrity_out_of_range_raises(self):
        author_id = UserId.generate()
        novel = Novel.create(title="t", author_id=author_id)
        with pytest.raises(ValueError, match="Sanctuary integrity must be between 0 and 100"):
            novel.update_sanctuary_integrity(101)
        with pytest.raises(ValueError, match="Sanctuary integrity must be between 0 and 100"):
            novel.update_sanctuary_integrity(-1)

    def test_to_metadata(self):
        author_id = UserId.generate()
        novel = Novel.create(
            title="タイトル",
            author_id=author_id,
            genre="fantasy",
            catchcopy="キャッチ",
            synopsis="あらすじ",
            concept="コンセプト",
        )
        metadata = novel.to_metadata()
        assert metadata.novel_id == novel.id
        assert metadata.title == novel.title
        assert metadata.author_id == novel.author_id
        assert metadata.genre == novel.genre

    def test_novel_eq_same_id(self):
        author_id = UserId.generate()
        novel_id = NovelId.generate()
        n1 = Novel(
            id=novel_id,
            title=Title("a"),
            author_id=author_id,
            genre=Genre("g"),
            catchcopy=Catchcopy("c"),
            synopsis=Summary("s"),
            concept=Summary("c"),
        )
        n2 = Novel(
            id=novel_id,
            title=Title("b"),
            author_id=author_id,
            genre=Genre("g"),
            catchcopy=Catchcopy("c"),
            synopsis=Summary("s"),
            concept=Summary("c"),
        )
        assert n1 == n2
        assert hash(n1) == hash(n2)

    def test_novel_eq_diff_id(self):
        author_id = UserId.generate()
        n1 = Novel.create(title="a", author_id=author_id)
        n2 = Novel.create(title="a", author_id=author_id)
        assert n1 != n2


class TestChapter:
    """Chapter エンティティのテスト."""

    def test_create_chapter(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        chapter = Chapter.create(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title="第1話",
        )
        assert isinstance(chapter.id, NovelId)
        assert chapter.novel_id == novel_id
        assert chapter.branch_id == branch_id
        assert chapter.episode_number == 1
        assert chapter.title == Title("第1話")
        assert chapter.content == ""
        assert chapter.score_story is None
        assert chapter.is_anchor is False

    def test_chapter_episode_number_zero_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Episode number must be positive"):
            Chapter(
                id=NovelId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                episode_number=0,
                title=Title("x"),
            )

    def test_update_content_returns_new_instance(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        chapter = Chapter.create(novel_id, branch_id, 1, "タイトル")
        new_chapter = chapter.update_content("新しい本文")
        assert new_chapter is not chapter
        assert new_chapter.content == "新しい本文"
        assert new_chapter.id == chapter.id
        assert new_chapter.episode_number == chapter.episode_number

    def test_set_score_returns_new_instance(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        chapter = Chapter.create(novel_id, branch_id, 1, "タイトル")
        scored = chapter.set_score(85)
        assert scored is not chapter
        assert scored.score_story == 85
        assert chapter.score_story is None  # 元は変更されない

    def test_chapter_eq_same_id(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        chapter_id = NovelId.generate()
        c1 = Chapter(
            id=chapter_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title=Title("t"),
        )
        c2 = Chapter(
            id=chapter_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title=Title("t"),
        )
        assert c1 == c2
        assert hash(c1) == hash(c2)


class TestEpisode:
    """Episode エンティティのテスト."""

    def test_create_episode(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        episode = Episode.create(
            novel_id=novel_id,
            branch_id=branch_id,
            number=3,
            title="第3話",
        )
        assert isinstance(episode.id, NovelId)
        assert episode.number == 3
        assert episode.title == Title("第3話")
        assert episode.tension == 50
        assert episode.catharsis == 0
        assert episode.status == "planned"

    def test_episode_number_zero_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Episode number must be positive"):
            Episode(
                id=NovelId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                number=0,
                title=Title("x"),
            )


class TestVolume:
    """Volume エンティティのテスト."""

    def test_create_volume(self):
        novel_id = NovelId.generate()
        volume = Volume(
            id=NovelId.generate(),
            novel_id=novel_id,
            number=1,
            title="第1巻",
            start_episode=1,
            end_episode=10,
        )
        assert volume.number == 1
        assert volume.title == "第1巻"
        assert volume.start_episode == 1
        assert volume.end_episode == 10
        assert volume.summary == ""

    def test_volume_number_zero_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="Volume number must be positive"):
            Volume(
                id=NovelId.generate(),
                novel_id=novel_id,
                number=0,
                title=Title("t"),
                start_episode=1,
                end_episode=10,
            )

    def test_volume_start_episode_zero_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="Start episode must be positive"):
            Volume(
                id=NovelId.generate(),
                novel_id=novel_id,
                number=1,
                title=Title("t"),
                start_episode=0,
                end_episode=10,
            )

    def test_volume_end_before_start_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="End episode must be >= start episode"):
            Volume(
                id=NovelId.generate(),
                novel_id=novel_id,
                number=1,
                title=Title("t"),
                start_episode=10,
                end_episode=5,
            )
