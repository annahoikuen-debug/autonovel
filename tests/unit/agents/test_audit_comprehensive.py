"""Comprehensive unit tests for src/agents/audit.py covering DeAIAuditor, InternalLogicValidator, LogicalAuditor, and PlotIntegrityMonitor helper methods."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.audit import (
    DeAIAuditor,
    InternalLogicValidator,
    LogicalAuditor,
    PlotIntegrityMonitor,
)
from src.models.audit import (
    CausalityAuditResult,
    CausalityLink,
    ForeshadowingItem,
    LogicalAuditIssueList,
    PromptPatch,
)
from src.models.graph_schemas import GraphExtractionResult, Entity, Relationship
from src.models.sharp_edge import SharpEdgeSpec


# ==============================================================================
# DeAIAuditor Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_deai_auditor_with_edge_preserver_semantic():
    """DeAIAuditor with edge_preserver uses semantic mode."""
    mock_edge_preserver = AsyncMock()
    mock_edge_preserver.check_edges_preserved.return_value = ([], 0)  # no lost edges, score
    auditor = DeAIAuditor(edge_preserver=mock_edge_preserver, llm=None, prompt_manager=None)

    is_valid, feedback = await auditor.audit(
        content="some content",
        before_content="before",
        edges=[SharpEdgeSpec(edge_type="ending_pullback", description="余韻のある終わり方")],
    )
    assert is_valid is True
    assert feedback == "OK"
    mock_edge_preserver.check_edges_preserved.assert_awaited_once()


@pytest.mark.asyncio
async def test_deai_auditor_with_emotional_hook():
    """DeAIAuditor checks emotional hook edges."""
    mock_edge_preserver = AsyncMock()
    mock_edge_preserver.check_edges_preserved.return_value = ([], 0)
    auditor = DeAIAuditor(edge_preserver=mock_edge_preserver, llm=None, prompt_manager=None)

    class Hook:
        one_line_intent = "hook intent"

    is_valid, feedback = await auditor.audit(
        content="content",
        before_content="before",
        emotional_hook=Hook(),
    )
    assert is_valid is True
    assert feedback == "OK"
    # Should have been called for hook edges
    mock_edge_preserver.check_edges_preserved.assert_awaited()


@pytest.mark.asyncio
async def test_deai_auditor_lost_edge_semantic():
    """DeAIAuditor returns False when edge lost in semantic mode."""
    lost_edge = SharpEdgeSpec(edge_type="ending_pullback", description="余韻のある終わり方")
    mock_edge_preserver = AsyncMock()
    mock_edge_preserver.check_edges_preserved.return_value = ([lost_edge], 0.8)
    auditor = DeAIAuditor(edge_preserver=mock_edge_preserver, llm=None, prompt_manager=None)

    is_valid, feedback = await auditor.audit(
        content="content",
        before_content="before",
        edges=[lost_edge],
    )
    assert is_valid is False
    assert "ending_pullback" in feedback
    assert "削られました" in feedback


@pytest.mark.asyncio
async def test_deai_auditor_with_llm_generate_json():
    """DeAIAuditor uses llm.generate_json when prompt_manager present."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "metadata": {"is_valid": False, "feedback": "LLM feedback"}
    }
    mock_pm = MagicMock()
    mock_pm.build_critic_feedback_prompt.return_value = "prompt"
    auditor = DeAIAuditor(llm=mock_llm, prompt_manager=mock_pm)

    is_valid, feedback = await auditor.audit("text")
    assert is_valid is False
    assert feedback == "LLM feedback"
    mock_pm.build_critic_feedback_prompt.assert_called_once_with(
        issue_list=None, draft_content="text", blueprint="text"
    )
    mock_llm.generate_json.assert_awaited_once_with(purpose="audit", prompt="prompt")


@pytest.mark.asyncio
async def test_deai_auditor_with_llm_callable():
    """DeAIAuditor uses llm as callable when no generate_json."""
    mock_llm = AsyncMock()
    mock_llm.return_value = {
        "metadata": {"is_valid": True, "feedback": "Callable OK"}
    }
    mock_pm = MagicMock()
    mock_pm.build_critic_feedback_prompt.return_value = "prompt"
    auditor = DeAIAuditor(llm=mock_llm, prompt_manager=mock_pm)

    is_valid, feedback = await auditor.audit("text")
    assert is_valid is True
    assert feedback == "Callable OK"
    mock_llm.assert_awaited_once_with(purpose="audit", prompt="prompt")


@pytest.mark.asyncio
async def test_deai_auditor_no_llm_no_pm():
    """DeAIAuditor with no LLM and no prompt manager returns OK."""
    auditor = DeAIAuditor(llm=None, prompt_manager=None)
    is_valid, feedback = await auditor.audit("anything")
    assert is_valid is True
    assert feedback == "OK"


# ==============================================================================
# InternalLogicValidator Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_internal_logic_validator_stubs():
    """InternalLogicValidator stub methods return expected values."""
    validator = InternalLogicValidator()
    # validate_alibi_and_timeline
    ok, issues = await validator.validate_alibi_and_timeline("bp", "script")
    assert ok is True
    assert issues == []
    # check_information_asymmetry
    ok2, issues2 = await validator.check_information_asymmetry("past", "curr")
    assert ok2 is True
    assert issues2 == []


# ==============================================================================
# LogicalAuditor Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_logical_auditor_no_pm():
    """LogicalAuditor without prompt manager returns default guidance."""
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor(pm=None)
    fb = await auditor.generate_critic_feedback(
        LogicalAuditIssueList(issues=[]), "draft", "blueprint"
    )
    assert "Prompt manager not configured" in fb.rewrite_guidance


@pytest.mark.asyncio
async def test_logical_auditor_with_pm_and_generate_json():
    """LogicalAuditor with prompt manager and llm.generate_json."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "metadata": {
            "rewrite_guidance": "Add detail",
            "pov_stability": 0.8,
            "empathy_gap": 0.2,
            "curiosity_hook_rate": 0.7,
            "sensory_density": 0.6,
            "catharsis_density": 0.9,
        }
    }
    mock_pm = MagicMock()
    mock_pm.build_critic_feedback_prompt = AsyncMock(return_value="prompt")
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor(pm=mock_pm, llm=mock_llm)

    fb = await auditor.generate_critic_feedback(
        LogicalAuditIssueList(issues=[]), "draft", "blueprint"
    )
    assert fb.rewrite_guidance == "Add detail"
    assert fb.pov_stability == 0.8
    assert fb.empathy_gap == 0.2
    assert fb.curiosity_hook_rate == 0.7
    assert fb.sensory_density == 0.6
    assert fb.catharsis_density == 0.9
    mock_pm.build_critic_feedback_prompt.assert_awaited_once_with(
        issue_list=LogicalAuditIssueList(issues=[]),
        draft_content="draft",
        blueprint="blueprint",
    )
    mock_llm.generate_json.assert_awaited_once_with(purpose="critic", prompt="prompt")


@pytest.mark.asyncio
async def test_logical_auditor_with_pm_and_callable_llm():
    """LogicalAuditor with prompt manager and callable llm."""
    mock_llm = AsyncMock()
    mock_llm.return_value = {
        "metadata": {"rewrite_guidance": "Callable guidance"}
    }
    mock_pm = MagicMock()
    mock_pm.build_critic_feedback_prompt = AsyncMock(return_value="prompt")
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor(pm=mock_pm, llm=mock_llm)

    fb = await auditor.generate_critic_feedback(
        LogicalAuditIssueList(issues=[]), "draft", "blueprint"
    )
    assert fb.rewrite_guidance == "Callable guidance"
    mock_llm.assert_awaited_once_with(purpose="critic", prompt="prompt")


@pytest.mark.asyncio
async def test_logical_auditor_stubs():
    """LogicalAuditor stub methods."""
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor()
    ok, issues = await auditor.validate_alibi_and_timeline("bp", "script")
    assert ok is True
    assert issues == []
    ok2, issues2 = await auditor.check_information_asymmetry("past", "curr")
    assert ok2 is True
    assert issues2 == []


@pytest.mark.asyncio
async def test_logical_auditor_analyze_tension_wave_no_repo():
    """analyze_tension_wave returns default pattern when repo is None."""
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor()
    pattern = await auditor.analyze_tension_wave(book_id=1, ep_range=(1, 5))
    # Should return a NarrativeWavePattern instance
    from src.models.audit import NarrativeWavePattern
    assert isinstance(pattern, NarrativeWavePattern)


@pytest.mark.asyncio
async def test_logical_auditor_score_narrative_metrics_empty_content():
    """score_narrative_metrics returns default scores for empty content."""
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor()
    scores = await auditor.score_narrative_metrics(
        book_id=1, branch_id=1, ep_num=1, scene_num=1, scene_content=""
    )
    assert len(scores) == 6
    metric_names = {s["metric_name"] for s in scores}
    assert metric_names == {
        "immersion_score",
        "pov_stability",
        "empathy_gap",
        "curiosity_hook_rate",
        "sensory_density",
        "catharsis_density",
    }
    # immersion_score should be 0.0 (default)
    immersion = next(s for s in scores if s["metric_name"] == "immersion_score")
    assert immersion["score"] == 0.0
    # empathy_gap default 1.0
    empathy = next(s for s in scores if s["metric_name"] == "empathy_gap")
    assert empathy["score"] == 1.0


@pytest.mark.asyncio
async def test_logical_auditor_score_narrative_metrics_with_llm():
    """score_narrative_metrics uses LLM when content provided."""
    # We'll mock the LLM call inside the method
    mock_llm = AsyncMock()
    mock_llm.return_value = {
        "metadata": {
            "pov_stability": 0.9,
            "empathy_gap": 0.1,
            "curiosity_hook_rate": 0.8,
            "sensory_density": 0.7,
            "catharsis_density": 0.6,
        }
    }
    with pytest.warns(DeprecationWarning, match="LogicalAuditor is deprecated"):
        auditor = LogicalAuditor(llm=mock_llm)
    # Patch the ImmersionScore calculation? We'll just call and check that llm was called.
    scores = await auditor.score_narrative_metrics(
        book_id=1, branch_id=1, ep_num=1, scene_num=1, scene_content="Hello world"
    )
    assert mock_llm.awaited
    # Verify that the scores reflect the mocked values (approx)
    immersion = next(s for s in scores if s["metric_name"] == "immersion_score")
    # immersion score is weighted sum; we can't assert exact without knowing weights,
    # but we can assert it's between 0 and 1.
    # ImmersionScore.calculate_total は 0.0-100.0 スケールの値を返す
    assert 0.0 <= immersion["score"] <= 100.0
    pov = next(s for s in scores if s["metric_name"] == "pov_stability")
    assert pov["score"] == 0.9
    empathy = next(s for s in scores if s["metric_name"] == "empathy_gap")
    assert empathy["score"] == 0.1


# ==============================================================================
# PlotIntegrityMonitor Helper Method Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_plot_integrity_monitor_extract_keywords_mock():
    """extract_keywords calls extraction_service and returns entity names."""
    mock_extract = AsyncMock()
    mock_result = GraphExtractionResult(
        entities=[
            Entity(name="アルス", type="Character", description="", properties={}),
            Entity(name="聖剣", type="Item", description="", properties={}),
            Entity(name="王都", type="Location", description="", properties={}),
        ],
        relationships=[],
        plot_summary="",
    )
    mock_extract.extract_graph_from_text.return_value = mock_result
    # モックはインスタンス生成前にパッチ適用し、本物のサービスがバインドされないようにする
    with patch("src.agents.audit.extraction_service", mock_extract):
        monitor = PlotIntegrityMonitor()
        keywords = await monitor.extract_keywords("アルスは聖剣を持って王都へ。")
    assert isinstance(keywords, list)
    assert "アルス" in keywords
    assert "聖剣" in keywords
    assert "王都" in keywords
    mock_extract.extract_graph_from_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_plot_integrity_monitor_extract_keywords_error():
    """extract_keywords returns empty list on extraction failure."""
    mock_extract = AsyncMock()
    mock_extract.extract_graph_from_text.side_effect = Exception("boom")
    with patch("src.agents.audit.extraction_service", mock_extract):
        monitor = PlotIntegrityMonitor()
        keywords = await monitor.extract_keywords("text")
    assert keywords == []


@pytest.mark.asyncio
async def test_plot_integrity_monitor_check_integrity_error_handling():
    """check_integrity returns safe result on unexpected error."""
    monitor = PlotIntegrityMonitor()
    # Make extract_keywords raise
    with patch.object(monitor, "extract_keywords", AsyncMock(side_effect=Exception("fail"))):
        is_ok, score, result = await monitor.check_integrity(
            [], "blueprint", "content", book_id=1, ep_num=1
        )
        # Should return safe values
        assert is_ok is True
        assert score == 1.0
        assert result.is_consistent is True
        assert result.contradictions == ["監査エラー: fail"]


@pytest.mark.asyncio
async def test_plot_integrity_monitor_extract_causality_links_no_llm():
    """_extract_causality_links returns empty list when LLM not configured."""
    monitor = PlotIntegrityMonitor(llm=None)
    links = await monitor._extract_causality_links("text", source="content")
    assert links == []


@pytest.mark.asyncio
async def test_plot_integrity_monitor_extract_causality_links_with_llm():
    """_extract_causality_links parses LLM output."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = {
        "metadata": {
            "causality_links": [
                {
                    "cause_entity": "A",
                    "cause_event": "cause",
                    "effect_entity": "B",
                    "effect_event": "effect",
                    "confidence": 0.8,
                }
            ]
        }
    }
    monitor = PlotIntegrityMonitor(llm=mock_llm)
    links = await monitor._extract_causality_links("text", source="blueprint")
    assert len(links) == 1
    link = links[0]
    assert link.cause_entity == "A"
    assert link.cause_event == "cause"
    assert link.effect_entity == "B"
    assert link.effect_event == "effect"
    assert link.confidence == 0.8
    assert link.source == "blueprint"


@pytest.mark.asyncio
async def test_plot_integrity_monitor_extract_causality_links_llm_callable():
    """_extract_causality_links works with callable LLM."""
    mock_llm = AsyncMock()
    mock_llm.return_value = {
        "metadata": {
            "causality_links": [
                {
                    "cause_entity": "X",
                    "cause_event": "x",
                    "effect_entity": "Y",
                    "effect_event": "y",
                    "confidence": 0.9,
                }
            ]
        }
    }
    monitor = PlotIntegrityMonitor(llm=mock_llm)
    links = await monitor._extract_causality_links("text", source="content")
    assert len(links) == 1
    link = links[0]
    assert link.cause_entity == "X"
    assert link.source == "content"
    mock_llm.assert_awaited_once()
    assert mock_llm.await_args.kwargs.get("purpose") == "causality_extraction"
    assert "text" in mock_llm.await_args.kwargs.get("prompt", "")


@pytest.mark.asyncio
async def test_plot_integrity_monitor_diff_graphs_basic():
    """_diff_graphs computes basic differences."""
    monitor = PlotIntegrityMonitor()
    # Mock extraction service to return two different results
    bp_entities = [Entity(name="A", type="Character", description="", properties={})]
    bp_rels = [Relationship(source="A", target="B", type="POSSESSES", detail="")]
    bp_result = GraphExtractionResult(entities=bp_entities, relationships=bp_rels, plot_summary="")
    ct_entities = [Entity(name="A", type="Character", description="", properties={}), Entity(name="C", type="Character", description="", properties={})]
    ct_rels = [Relationship(source="A", target="C", type="POSSESSES", detail="")]
    ct_result = GraphExtractionResult(entities=ct_entities, relationships=ct_rels, plot_summary="")
    mock_extract = AsyncMock()
    mock_extract.extract_graph_from_text.side_effect = [bp_result, ct_result]
    with patch("src.agents.audit.extraction_service", mock_extract):
        monitor = PlotIntegrityMonitor()
        diff = await monitor._diff_graphs("bp", "ct")
    assert diff.missing_entities == set()  # A in both
    assert diff.extra_entities == {"C"}
    assert diff.missing_relations == {("A", "B", "POSSESSES")}
    assert diff.extra_relations == {("A", "C", "POSSESSES")}


@pytest.mark.asyncio
async def test_plot_integrity_monitor_verify_causality_chains_edge_cases():
    """_verify_causality_chains handles terminal and initial entities."""
    monitor = PlotIntegrityMonitor()
    # Terminal entity: effect event contains death keyword
    link_death = CausalityLink(
        cause_entity="hero", cause_event="fight", effect_entity="enemy", effect_event="死亡", source="blueprint"
    )
    broken = monitor._verify_causality_chains([link_death])
    # enemy is terminal (death) so should NOT be broken even though it has input and no output
    assert broken == []
    # Initial entity: cause event contains start keyword
    link_start = CausalityLink(
        cause_entity="hero", cause_event="旅立ち", effect_entity="world", effect_event="adventure", source="blueprint"
    )
    broken2 = monitor._verify_causality_chains([link_start])
    # hero is initial (旅立ち) so should NOT be broken
    assert broken2 == []
    # Non-terminal, non-initial with only input -> broken
    link_mid = CausalityLink(
        cause_entity="A", cause_event="a", effect_entity="B", effect_event="b", source="blueprint"
    )
    broken3 = monitor._verify_causality_chains([link_mid])
    # B has input but no output, not terminal -> broken
    assert len(broken3) == 1
    assert broken3[0].effect_entity == "B"


def test_plot_integrity_monitor_is_terminal_entity():
    monitor = PlotIntegrityMonitor()
    # Death keywords
    link = CausalityLink(
        cause_entity="A", cause_event="attack", effect_entity="B", effect_event="死亡", source="blueprint"
    )
    assert monitor._is_terminal_entity("B", [link]) is True
    link2 = CausalityLink(
        cause_entity="A", cause_event="attack", effect_entity="B", effect_event="消滅", source="blueprint"
    )
    assert monitor._is_terminal_entity("B", [link2]) is True
    link3 = CausalityLink(
        cause_entity="A", cause_event="attack", effect_entity="B", effect_event="完結", source="blueprint"
    )
    assert monitor._is_terminal_entity("B", [link3]) is True
    # Not terminal
    link4 = CausalityLink(
        cause_entity="A", cause_event="attack", effect_entity="B", effect_event="負傷", source="blueprint"
    )
    assert monitor._is_terminal_entity("B", [link4]) is False


def test_plot_integrity_monitor_is_initial_entity():
    monitor = PlotIntegrityMonitor()
    link = CausalityLink(
        cause_entity="A", cause_event="旅立ち", effect_entity="B", effect_event="something", source="blueprint"
    )
    assert monitor._is_initial_entity("A", [link]) is True
    link2 = CausalityLink(
        cause_entity="A", cause_event="発見", effect_entity="B", effect_event="something", source="blueprint"
    )
    assert monitor._is_initial_entity("A", [link2]) is True
    link3 = CausalityLink(
        cause_entity="A", cause_event="攻撃", effect_entity="B", effect_event="something", source="blueprint"
    )
    assert monitor._is_initial_entity("A", [link3]) is False


@pytest.mark.asyncio
async def test_plot_integrity_monitor_detect_foreshadowing_and_contradictions():
    """_detect_foreshadowing_and_contradictions returns lists."""
    monitor = PlotIntegrityMonitor()
    # Mock extraction service to return blueprint with missing entities
    bp_entities = [
        Entity(name="アイテムX", type="Item", description="レアアイテム", properties={"rarity": "legendary"}),
        Entity(name="イベントY", type="Event", description="クライマックス", properties={"is_climax": True}),
    ]
    bp_rels = []
    bp_result = GraphExtractionResult(entities=bp_entities, relationships=bp_rels, plot_summary="")
    # Content extraction returns empty (so all bp entities missing)
    ct_result = GraphExtractionResult(entities=[], relationships=[], plot_summary="")
    mock_extract = AsyncMock()
    mock_extract.extract_graph_from_text.side_effect = [bp_result, ct_result]
    graph_diff = MagicMock()
    # Blueprint にのみ存在するエンティティを明示設定
    graph_diff.missing_entities = {"アイテムX", "イベントY"}
    graph_diff.missing_relations = set()
    graph_diff.property_conflicts = {}
    with patch("src.agents.audit.extraction_service", mock_extract):
        monitor = PlotIntegrityMonitor()
        foreshadowing, contradictions = await monitor._detect_foreshadowing_and_contradictions(
            blueprint="bp", content="ct", graph_diff=graph_diff, ep_num=3
        )
    # Should detect foreshadowing for legendary item and climax event
    assert len(foreshadowing) >= 1
    names = {fs.entity_name for fs in foreshadowing}
    assert "アイテムX" in names or "イベントY" in names
    # Contradictions from property_conflicts? graph_diff is MagicMock, we can set return
    # For simplicity, we just check that it returns lists
    assert isinstance(foreshadowing, list)
    assert isinstance(contradictions, list)


@pytest.mark.asyncio
async def test_plot_integrity_monitor_generate_patches_all_types():
    """_generate_patches creates patches for broken chains, foreshadowing, contradictions."""
    monitor = PlotIntegrityMonitor()
    broken = [CausalityLink(cause_entity="A", cause_event="a", effect_entity="B", effect_event="b", source="content")]
    fs = [ForeshadowingItem(entity_name="X", setup_chapter=1, setup_context="ctx", expected_payoff="payoff")]
    contradictions = ["[X.prop] Blueprint: 1 vs Content: 2"]
    patches = await monitor._generate_patches(broken, fs, contradictions)
    assert len(patches) == 3
    targets = {p.target_prompt for p in patches}
    assert targets == {"writing_director", "plot_expansion", "bible_update"}


@pytest.mark.asyncio
async def test_plot_integrity_monitor_submit_patches():
    """_submit_patches persists pending patches and returns IDs."""
    monitor = PlotIntegrityMonitor()
    # Mock the database components
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_pending = MagicMock()
    mock_pending.id = 42

    # UnitOfWork を async context manager として模倣するモック
    class _FakeUOW:
        session = mock_session

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    with patch("src.backend.database.uow.UnitOfWork", return_value=_FakeUOW()), \
         patch("src.backend.database.models.PendingPatch", return_value=mock_pending), \
         patch("src.core.container.AppContainer") as mock_container:
        mock_container.db.return_value = MagicMock()
        patch_ids = await monitor._submit_patches(book_id=99, patches=[
            PromptPatch(target_prompt="t1", patch_content="c1", reasoning="r1"),
            PromptPatch(target_prompt="t2", patch_content="c2", reasoning="r2"),
        ])
        assert patch_ids == [42, 42]  # same mock returned twice
        assert mock_session.add.call_count == 2
        assert mock_session.flush.await_count == 2
        assert mock_session.commit.await_count == 1


def test_plot_integrity_monitor_calculate_score_edge_cases():
    monitor = PlotIntegrityMonitor()
    # No links, no issues -> 1.0
    assert monitor._calculate_score([], [], [], []) == 1.0
    # Broken chains only
    links = [CausalityLink(cause_entity="A", cause_event="a", effect_entity="B", effect_event="b", source="blueprint") for _ in range(4)]
    broken = links[:2]  # 50% broken
    score = monitor._calculate_score(broken, [], [], links)
    # broken_ratio = 0.5, penalty = 0.5 * 0.4 = 0.2 -> score 0.8
    assert score == pytest.approx(0.8, rel=0.01)
    # Foreshadowing Critical and Major
    fs_critical = [ForeshadowingItem(entity_name="X", setup_chapter=1, setup_context="c", expected_payoff="p", importance="Critical")]
    fs_major = [ForeshadowingItem(entity_name="Y", setup_chapter=1, setup_context="c", expected_payoff="p", importance="Major")]
    score2 = monitor._calculate_score([], fs_critical + fs_major, [], [])
    # Critical: 0.15, Major: 0.08 -> total 0.23 penalty -> 0.77
    assert score2 == pytest.approx(0.77, rel=0.01)
    # Contradictions
    score3 = monitor._calculate_score([], [], ["c1", "c2", "c3"], [])
    # 0.1 * 3 = 0.3 penalty -> 0.7
    assert score3 == pytest.approx(0.7, rel=0.01)
    # Combined
    score4 = monitor._calculate_score(broken, fs_critical, ["c1"], links)
    # broken penalty 0.2, critical 0.15, contradictions 0.1 -> total 0.45 -> 0.55
    assert score4 == pytest.approx(0.55, rel=0.01)


@pytest.mark.asyncio
async def test_plot_integrity_monitor_audit_setting_causality():
    """audit_setting_causality calls check_integrity and converts result."""
    monitor = PlotIntegrityMonitor()
    # Mock check_integrity to return a known result
    mock_result = CausalityAuditResult(
        is_consistent=False,
        score=0.6,
        causality_links=[],
        broken_chains=[CausalityLink(cause_entity="A", cause_event="a", effect_entity="B", effect_event="b", source="content")],
        unresolved_foreshadowing=[ForeshadowingItem(entity_name="アイテム", setup_chapter=2, setup_context="ctx", expected_payoff="payoff")],
        contradictions=["矛盾テキスト"],
    )
    with patch.object(monitor, "check_integrity", AsyncMock(return_value=(False, 0.6, mock_result))):
        is_ok, reason, failures = await monitor.audit_setting_causality(
            content="content", world_settings="world", blueprint="blueprint"
        )
        assert is_ok is False
        assert isinstance(reason, str)
        assert "因果鎖切れ" in reason
        assert "伏線未回収" in reason
        assert "設定矛盾" in reason
        assert isinstance(failures, list)
        # Should have 3 failures: one broken chain, one foreshadowing, one contradiction
        assert len(failures) == 3
        # Check structure
        for f in failures:
            assert "rule" in f
            assert "gap" in f
            assert "fragment" in f


@pytest.mark.asyncio
async def test_plot_integrity_monitor_run_constraint_unit_tests():
    """run_constraint_unit_tests checks simple substring constraint."""
    monitor = PlotIntegrityMonitor()
    # No constraints
    ok, failures = await monitor.run_constraint_unit_tests("content", [])
    assert ok is True
    assert failures == []
    # Empty content
    ok2, failures2 = await monitor.run_constraint_unit_tests("", [{"constraint": "hello"}])
    assert ok2 is True  # because empty content? Actually constraint not in empty content -> failure
    # Wait: the method returns True if no failures? Let's check code: if not active_constraints or not content: return True, []
    # So if content is empty string, it returns True, [] (early exit). That's a design choice.
    # We'll test with non-empty content.
    ok3, failures3 = await monitor.run_constraint_unit_tests("hello world", [{"constraint": "world"}])
    assert ok3 is True
    assert failures3 == []
    ok4, failures4 = await monitor.run_constraint_unit_tests("hello", [{"constraint": "world"}])
    assert ok4 is False
    assert len(failures4) == 1
    f = failures4[0]
    assert f["constraint_index"] == 0
    assert "制約未満足" in f["reason"]
    assert f["violating_snippet"] == "..."
    # Error handling
    with patch.object(monitor, "llm", None):  # not used
        ok5, failures5 = await monitor.run_constraint_unit_tests("content", [{"constraint": "test"}])
        # Should still work (no LLM needed)
        assert isinstance(ok5, bool)
        assert isinstance(failures5, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
