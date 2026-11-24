"""src/domain/entities/plot.py (Plot / PlotPoint / Arc / PlotStatus / ChainPhase) の単体テスト."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities.plot import Arc, ChainPhase, Plot, PlotPoint, PlotStatus
from src.domain.value_objects.ids import NovelId, PlotId
from src.domain.value_objects.text import MarkdownText, TextContent, Title


class TestPlotStatus:
    """PlotStatus 列挙体のテスト."""

    def test_values(self):
        assert PlotStatus.PLANNED.value == "planned"
        assert PlotStatus.WRITING.value == "writing"
        assert PlotStatus.COMPLETED.value == "completed"
        assert PlotStatus.REVISED.value == "revised"
        assert PlotStatus.LOCKED.value == "locked"

    def test_rank(self):
        assert PlotStatus.PLANNED.rank() == 1
        assert PlotStatus.WRITING.rank() == 2
        assert PlotStatus.COMPLETED.rank() == 3
        assert PlotStatus.REVISED.rank() == 4
        assert PlotStatus.LOCKED.rank() == 5

    def test_rank_order_matches_progression(self):
        assert PlotStatus.PLANNED.rank() < PlotStatus.WRITING.rank()
        assert PlotStatus.WRITING.rank() < PlotStatus.COMPLETED.rank()
        assert PlotStatus.COMPLETED.rank() < PlotStatus.REVISED.rank()
        assert PlotStatus.REVISED.rank() < PlotStatus.LOCKED.rank()


class TestChainPhase:
    """ChainPhase 列挙体のテスト."""

    def test_values(self):
        assert ChainPhase.FRICITON.value == "Friction"
        assert ChainPhase.TURN.value == "Turn"
        assert ChainPhase.COUNTER_TURN.value == "CounterTurn"
        assert ChainPhase.RESOLUTION.value == "Resolution"
        assert ChainPhase.CATHARSIS.value == "Catharsis"
        assert ChainPhase.MICRO_CATHARSIS.value == "MicroCatharsis"


class TestPlotCreate:
    """Plot.create ファクトリメソッドのテスト."""

    def test_create_plot(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title="プロット",
            summary="概要",
        )
        assert isinstance(plot.id, PlotId)
        assert plot.novel_id == novel_id
        assert plot.branch_id == branch_id
        assert plot.episode_number == 1
        assert plot.title == Title("プロット")
        assert plot.summary.content == "概要"
        assert plot.one_line_summary == ""
        assert isinstance(plot.detailed_blueprint, MarkdownText)
        assert isinstance(plot.thought_process, MarkdownText)
        assert plot.tension_score.value == 50
        assert plot.status == PlotStatus.PLANNED
        assert plot.is_catharsis is False
        assert isinstance(plot.created_at, datetime)
        assert isinstance(plot.updated_at, datetime)
        assert plot.created_at == plot.updated_at

    def test_create_plot_episode_number_zero_raises(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        with pytest.raises(ValueError, match="Episode number must be positive"):
            Plot(
                id=PlotId.generate(),
                novel_id=novel_id,
                branch_id=branch_id,
                episode_number=0,
                title=Title("x"),
                summary=TextContent("s"),
            )


class TestPlotMethods:
    """Plot のメソッドテスト."""

    def test_update_content(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "タイトル", "概要")
        before = plot.updated_at
        plot.update_content(
            title="新タイトル",
            summary="新概要",
            one_line_summary="一言",
        )
        assert plot.title == Title("新タイトル")
        assert plot.summary.content == "新概要"
        assert plot.one_line_summary == "一言"
        assert plot.updated_at >= before

    def test_set_tension(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.set_tension(80, delta=30)
        assert plot.tension_score.value == 80
        assert plot.tension_score.delta == 30

    def test_set_catharsis(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.set_catharsis(85, catharsis_type="クライマックス")
        assert plot.catharsis == 85
        assert plot.catharsis_type == "クライマックス"
        assert plot.is_catharsis is True

    def test_set_catharsis_below_threshold(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.set_catharsis(50)
        assert plot.is_catharsis is False

    def test_change_status(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        assert plot.status == PlotStatus.PLANNED
        plot.change_status(PlotStatus.WRITING)
        assert plot.status == PlotStatus.WRITING
        plot.change_status(PlotStatus.COMPLETED)
        assert plot.status == PlotStatus.COMPLETED

    def test_lock_unlock(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        assert plot.is_locked is False
        plot.lock()
        assert plot.is_locked is True
        plot.unlock()
        assert plot.is_locked is False

    def test_set_chain_phase(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.set_chain_phase(ChainPhase.TURN)
        assert plot.current_chain_phase == ChainPhase.TURN

    def test_add_remove_scene(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.add_scene("scene1")
        plot.add_scene("scene2")
        assert plot.scenes == ["scene1", "scene2"]
        assert plot.remove_scene(0) is True
        assert plot.scenes == ["scene2"]
        assert plot.remove_scene(99) is False
        assert plot.remove_scene(-1) is False

    def test_update_scores(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.update_scores(
            state_integrity=80,
            emotional_resonance=70,
            thematic_depth=90,
            literary_beauty=60,
            erotic_intensity=30,
        )
        assert plot.state_integrity_score == 80
        assert plot.emotional_resonance_score == 70
        assert plot.thematic_depth_score == 90
        assert plot.literary_beauty_score == 60
        assert plot.erotic_intensity == 30

    def test_update_scores_clamp(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.update_scores(state_integrity=200, emotional_resonance=-50)
        assert plot.state_integrity_score == 100
        assert plot.emotional_resonance_score == 0

    def test_add_healed_field(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "t", "s")
        plot.add_healed_field("field1")
        plot.add_healed_field("field2")
        assert plot.healed_fields == ["field1", "field2"]
        # 重複は追加されない
        plot.add_healed_field("field1")
        assert plot.healed_fields == ["field1", "field2"]

    def test_to_dict(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot = Plot.create(novel_id, branch_id, 1, "タイトル", "概要")
        d = plot.to_dict()
        assert d["episode_number"] == 1
        assert d["title"] == "タイトル"
        assert d["summary"] == "概要"
        assert d["status"] == "planned"
        assert d["tension"] == 50
        assert d["is_catharsis"] is False
        assert "created_at" in d
        assert "updated_at" in d

    def test_plot_eq_same_id(self):
        novel_id = NovelId.generate()
        branch_id = NovelId.generate()
        plot_id = PlotId.generate()
        p1 = Plot(
            id=plot_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title=Title("a"),
            summary=TextContent("s"),
        )
        p2 = Plot(
            id=plot_id,
            novel_id=novel_id,
            branch_id=branch_id,
            episode_number=1,
            title=Title("b"),
            summary=TextContent("s"),
        )
        assert p1 == p2
        assert hash(p1) == hash(p2)


class TestPlotPoint:
    """PlotPoint エンティティのテスト."""

    def test_create_plot_point(self):
        plot_id = PlotId.generate()
        pp = PlotPoint(
            id=PlotId.generate(),
            plot_id=plot_id,
            order=0,
            description=TextContent("説明"),
            type="setup",
        )
        assert pp.order == 0
        assert pp.description.content == "説明"
        assert pp.type == "setup"
        assert pp.tension_contribution == 0
        assert pp.is_major is False

    def test_plot_point_order_negative_raises(self):
        plot_id = PlotId.generate()
        with pytest.raises(ValueError, match="Order must be non-negative"):
            PlotPoint(
                id=PlotId.generate(),
                plot_id=plot_id,
                order=-1,
                description=TextContent("s"),
                type="setup",
            )


class TestArc:
    """Arc エンティティのテスト."""

    def test_create_arc(self):
        novel_id = NovelId.generate()
        arc = Arc.create(
            novel_id=novel_id,
            name="メインアーク",
            description=TextContent("アーク説明"),
            start_episode=1,
            end_episode=10,
        )
        assert arc.name == "メインアーク"
        assert arc.description.content == "アーク説明"
        assert arc.start_episode == 1
        assert arc.end_episode == 10
        assert arc.arc_type == "main"
        assert arc.status == PlotStatus.PLANNED

    def test_create_arc_custom_type(self):
        novel_id = NovelId.generate()
        arc = Arc.create(
            novel_id=novel_id,
            name="サブアーク",
            description=TextContent("d"),
            start_episode=5,
            end_episode=8,
            arc_type="sub",
        )
        assert arc.arc_type == "sub"

    def test_get_span(self):
        novel_id = NovelId.generate()
        arc = Arc.create(
            novel_id=novel_id,
            name="a",
            description=TextContent("d"),
            start_episode=3,
            end_episode=7,
        )
        assert arc.get_span() == 5  # 7 - 3 + 1

    def test_contains_episode(self):
        novel_id = NovelId.generate()
        arc = Arc.create(
            novel_id=novel_id,
            name="a",
            description=TextContent("d"),
            start_episode=3,
            end_episode=7,
        )
        assert arc.contains_episode(3) is True
        assert arc.contains_episode(5) is True
        assert arc.contains_episode(7) is True
        assert arc.contains_episode(2) is False
        assert arc.contains_episode(8) is False

    def test_arc_empty_name_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="Arc name cannot be empty"):
            Arc(
                id=PlotId.generate(),
                novel_id=novel_id,
                name="   ",
                description=TextContent("d"),
                start_episode=1,
                end_episode=1,
            )

    def test_arc_start_episode_zero_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="Start episode must be positive"):
            Arc(
                id=PlotId.generate(),
                novel_id=novel_id,
                name="a",
                description=TextContent("d"),
                start_episode=0,
                end_episode=1,
            )

    def test_arc_end_before_start_raises(self):
        novel_id = NovelId.generate()
        with pytest.raises(ValueError, match="End episode must be >= start episode"):
            Arc(
                id=PlotId.generate(),
                novel_id=novel_id,
                name="a",
                description=TextContent("d"),
                start_episode=5,
                end_episode=3,
            )
