"""src/domain/entities/scene.py (Scene / SceneRole / SceneStatus) の単体テスト."""

from __future__ import annotations

import pytest

from src.domain.entities.scene import Scene, SceneRole, SceneStatus
from src.domain.value_objects.ids import NovelId, SceneId


class TestSceneRole:
    """SceneRole 列挙体のテスト."""

    def test_introduction_value(self):
        assert SceneRole.INTRODUCTION.value == "導入"

    def test_conflict_value(self):
        assert SceneRole.CONFLICT.value == "衝突"

    def test_hook_value(self):
        assert SceneRole.HOOK.value == "引き"


class TestSceneStatus:
    """SceneStatus 列挙体のテスト."""

    def test_planned_value(self):
        assert SceneStatus.PLANNED.value == "planned"

    def test_writing_value(self):
        assert SceneStatus.WRITING.value == "writing"

    def test_completed_value(self):
        assert SceneStatus.COMPLETED.value == "completed"

    def test_failed_value(self):
        assert SceneStatus.FAILED.value == "failed"


class TestSceneCreate:
    """Scene 生成クラスメソッドのテスト."""

    def test_create_introduction(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
        )
        assert isinstance(scene.id, SceneId)
        assert scene.novel_id == novel_id
        assert scene.branch_id == branch_id
        assert scene.episode_number == 1
        assert scene.scene_number == 1
        assert scene.role == SceneRole.INTRODUCTION
        assert scene.title == "導入"
        assert scene.target_word_count == 800
        assert scene.tension_start == 20
        assert scene.tension_end == 50
        assert scene.status == SceneStatus.PLANNED
        assert scene.status == SceneStatus.PLANNED
        assert scene.status != SceneStatus.COMPLETED
        assert len(scene.beats) == 3
        assert scene.beats == [
            "日常/現状の提示",
            "主人公の目的/動機の暗示",
            "小さな事件/違和感の導入",
        ]

    def test_create_conflict(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_conflict(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=2,
        )
        assert scene.scene_number == 2
        assert scene.role == SceneRole.CONFLICT
        assert scene.title == "衝突"
        assert scene.tension_start == 50
        assert scene.tension_end == 85
        assert len(scene.beats) == 3

    def test_create_hook(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_hook(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=3,
        )
        assert scene.scene_number == 3
        assert scene.role == SceneRole.HOOK
        assert scene.title == "引き"
        assert scene.tension_start == 85
        assert scene.tension_end == 95
        assert len(scene.beats) == 3

    def test_create_standard_triad(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scenes = Scene.create_standard_triad(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            target_word_count=2400,
        )
        assert len(scenes) == 3
        assert scenes[0].scene_number == 1
        assert scenes[1].scene_number == 2
        assert scenes[2].scene_number == 3
        # 2400 // 3 = 800 ずつ
        assert scenes[0].target_word_count == 800
        assert scenes[1].target_word_count == 800
        assert scenes[2].target_word_count == 800

    def test_create_standard_triad_with_custom_beats(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        custom_beats = {
            SceneRole.INTRODUCTION: ["カスタム導入1", "カスタム導入2"],
            SceneRole.CONFLICT: ["カスタム衝突1"],
            SceneRole.HOOK: ["カスタム引き1", "カスタム引き2", "カスタム引き3"],
        }
        scenes = Scene.create_standard_triad(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            custom_beats=custom_beats,
        )
        assert scenes[0].beats == ["カスタム導入1", "カスタム導入2"]
        assert scenes[1].beats == ["カスタム衝突1"]
        assert scenes[2].beats == ["カスタム引き1", "カスタム引き2", "カスタム引き3"]


class TestSceneValidation:
    """Scene のバリデーションテスト."""

    def test_scene_number_out_of_range_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Scene number must be 1, 2, or 3"):
            Scene(
                id=SceneId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                episode_number=1,
                scene_number=0,
                role=SceneRole.INTRODUCTION,
                title="x",
            )

    def test_scene_number_four_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Scene number must be 1, 2, or 3"):
            Scene(
                id=SceneId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                episode_number=1,
                scene_number=4,
                role=SceneRole.INTRODUCTION,
                title="x",
            )

    def test_target_word_count_below_min_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Target word count must be at least 100"):
            Scene(
                id=SceneId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                episode_number=1,
                scene_number=1,
                role=SceneRole.INTRODUCTION,
                title="x",
                target_word_count=50,
            )


class TestSceneStateTransitions:
    """Scene の状態遷移テスト."""

    def test_mark_writing(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(novel_id, branch_id, 1)
        assert scene.status == SceneStatus.PLANNED
        scene.mark_writing()
        assert scene.status == SceneStatus.WRITING

    def test_mark_completed_sets_content_and_word_count(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(novel_id, branch_id, 1)
        content = "これはシーンの本文です。"
        scene.mark_completed(content)
        assert scene.status == SceneStatus.COMPLETED
        assert scene.content == content
        assert scene.actual_word_count == len(content)

    def test_mark_failed(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(novel_id, branch_id, 1)
        scene.mark_failed("generation error")
        assert scene.status == SceneStatus.FAILED
        assert scene.generation_metadata["error"] == "generation error"


class TestSceneDerived:
    """Scene の派生プロパティ・メソッドテスト."""

    def test_get_tension_delta(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(novel_id, branch_id, 1)
        # introduction: tension_start=20, tension_end=50
        assert scene.get_tension_delta() == 30

    def test_to_dict(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene = Scene.create_introduction(novel_id, branch_id, 1)
        d = scene.to_dict()
        assert d["scene_number"] == 1
        assert d["role"] == "導入"
        assert d["status"] == "planned"
        assert d["tension_start"] == 20
        assert d["tension_end"] == 50
        assert d["tension_delta"] == 30
        assert d["beats"] == scene.beats
        assert "created_at" in d
        assert "updated_at" in d

    def test_eq_same_id(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        scene_id = SceneId.generate()
        s1 = Scene(
            id=scene_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            scene_number=1,
            role=SceneRole.INTRODUCTION,
            title="a",
        )
        s2 = Scene(
            id=scene_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            scene_number=1,
            role=SceneRole.INTRODUCTION,
            title="b",
        )
        assert s1 == s2
        assert hash(s1) == hash(s2)

    def test_eq_diff_id(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        s1 = Scene(
            id=SceneId.generate(),
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            scene_number=1,
            role=SceneRole.INTRODUCTION,
            title="a",
        )
        s2 = Scene(
            id=SceneId.generate(),
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            scene_number=1,
            role=SceneRole.INTRODUCTION,
            title="a",
        )
        assert s1 != s2
