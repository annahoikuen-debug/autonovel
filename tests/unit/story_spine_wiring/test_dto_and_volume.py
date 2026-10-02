"""DTO の結線と volume カウンタの確認。"""

import pytest


def _ctx():
    """WorkflowContext の必須引数をすべて満たす（既存テストと同じ最小構成）。"""
    from src.services.pipeline_base import WorkflowContext

    return WorkflowContext(
        genre="g", keywords="", archetype_key="exile_rise",
        target_eps=8, initial_limit=3, word_count=2500,
    )


def test_generate_plot_dto_accepts_spine_keys():
    from src.application.dtos.plot_dto import GeneratePlotDTO

    dto = GeneratePlotDTO(
        novel_id="n", branch_id="b",
        pattern_key="exile_rise", length_key="web_volume", market_key="web",
    )
    assert dto.pattern_key == "exile_rise"
    assert dto.length_key == "web_volume"
    assert dto.market_key == "web"


def test_generate_plot_dto_legacy_construction():
    """既存呼び出し（キーなし）が壊れていないこと。"""
    from src.application.dtos.plot_dto import GeneratePlotDTO

    dto = GeneratePlotDTO(novel_id="n", branch_id="b")
    assert dto.structure_type == "three_act"
    assert dto.pattern_key == ""
    assert dto.length_key == ""
    assert dto.market_key == ""


def test_workflow_context_has_volume_index():
    from src.services.pipeline_base import WorkflowContext

    ctx = _ctx()
    assert ctx.volume_index == 1
    assert ctx.current_volume == 1, "既存フィールドは後方互換のため残す"


def test_volume_index_increments():
    from src.services.pipeline_base import WorkflowContext

    ctx = _ctx()
    ctx.volume_index += 1
    assert ctx.volume_index == 2


def test_package_step_advances_volume_index():
    """納品 Step 完了で実際に巻が進むこと（増加箇所の存在確認）。"""
    from pathlib import Path

    src = Path("src/services/pipeline_steps.py").read_text(encoding="utf-8")
    assert "ctx.volume_index += 1" in src, "PackageStep で volume_index が増えていない"
