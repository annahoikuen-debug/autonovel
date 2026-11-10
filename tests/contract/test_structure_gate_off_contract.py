"""PLAN_S1 N3 の off 契約 — 構造ゲート配線が現行動作を変えないこと。

壊れ方: off なのに expand_macro_skeletons が gate を呼んで tension を変える /
DB 保存内容が変わる / gate の例外で macro 生成が落ちる → この契約が赤になる。
"""

from __future__ import annotations

from typing import List

import pytest

from src.engine.default_plot_expander import DefaultPlotExpander
from src.models.plot import EpisodeMacroSkeleton, PlotMacroBatch


def _macro_batch() -> PlotMacroBatch:
    return PlotMacroBatch(
        episodes=[
            EpisodeMacroSkeleton(
                ep_num=1,
                title="旅立ち",
                one_line_summary="村を出る",
                tension=20,
                current_chain_phase="Friction",
            ),
            EpisodeMacroSkeleton(
                ep_num=2,
                title="激突",
                one_line_summary="強敵と衝突",
                tension=95,
                current_chain_phase="Hate",
            ),
            EpisodeMacroSkeleton(
                ep_num=3,
                title="決着",
                one_line_summary="決着",
                tension=60,
                current_chain_phase="Fulfillment",
            ),
            EpisodeMacroSkeleton(
                ep_num=4,
                title="凪",
                one_line_summary="余韻",
                tension=60,
                current_chain_phase="Fulfillment",
            ),
        ]
    )


class _FakeRepo:
    def __init__(self, bible_dict=None):
        self.bible_dict = bible_dict if bible_dict is not None else {}
        self.created_plots: List[tuple] = []

    async def get_latest_bible(self, book_id):
        return self.bible_dict

    async def get_plot(self, branch_id, ep_num, book_id=None):
        return None

    async def create_or_replace_plot(self, book_id, ep_num, plot):
        self.created_plots.append((book_id, ep_num, plot))


class _FakeLLM:
    def __init__(self, batch: PlotMacroBatch):
        self.batch = batch
        self.prompts: List[str] = []

    async def generate_json(self, model, prompt, response_schema, reporter=None):
        self.prompts.append(prompt)
        return self.batch


class _FakePM:
    async def build_macro_plot_skeleton_prompt(self, bible_json_str, ep_range, book_id=None, spine=None, spine_quality=None):
        return "macro prompt"

    async def build_micro_scene_expander_prompt(self, **kwargs):
        return "micro prompt"


class _FakeReporter:
    def __init__(self):
        self.messages: List[tuple] = []

    def report(self, msg, level="info"):
        self.messages.append((msg, level))


def _build_expander(monkeypatch, batch: PlotMacroBatch):
    monkeypatch.setenv("AUTONOVEL_NARRATIVE_STRUCTURE_CONFIG", "config/narrative_structure.yaml")
    repo = _FakeRepo()
    llm = _FakeLLM(batch)
    expander = DefaultPlotExpander(repo=repo, pm=_FakePM(), llm=llm)
    return expander, repo, llm


@pytest.fixture(autouse=True)
def _reset_gate_cache():
    from src.engine.structure_gate import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


class TestOffContract:
    def test_off_mode_never_constructs_gate(self, monkeypatch):
        """off (既定) では gate インスタンスが生成されないこと (オーバーヘッドゼロ契約)。"""
        import src.engine.structure_gate as sg

        constructed: List[int] = []
        original = sg.NarrativeStructureGate

        class _Spy(original):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                constructed.append(1)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(sg, "NarrativeStructureGate", _Spy)
        expander, repo, _ = _build_expander(monkeypatch, _macro_batch())
        import asyncio

        asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        assert constructed == []

    def test_off_mode_db_content_identical_to_llm_output(self, monkeypatch):
        """off で LLM 応答の tension がそのまま DB 保存されること (補正なし)。"""
        expander, repo, _ = _build_expander(monkeypatch, _macro_batch())
        import asyncio

        skeletons = asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        assert [s.tension for s in skeletons] == [20, 95, 60, 60]
        saved_tensions = [plot.tension for _, _, plot in repo.created_plots]
        assert saved_tensions == [20, 95, 60, 60]

    def test_env_missing_defaults_to_off(self, monkeypatch):
        """NARRATIVE_STRUCTURE_GATE 未設定 = off であること。"""
        monkeypatch.delenv("NARRATIVE_STRUCTURE_GATE", raising=False)
        from src.engine.structure_gate import get_gate_mode

        assert get_gate_mode() == "off"

    def test_gate_exception_does_not_stop_expansion(self, monkeypatch):
        """gate 層の例外で macro 生成が落ちないこと (P3 fail-open)。"""
        import src.engine.structure_gate as sg

        def _raise(*args, **kwargs):
            raise RuntimeError("gate exploded")

        monkeypatch.setattr(sg, "get_gate_mode", lambda: "warn")
        monkeypatch.setattr(sg, "NarrativeStructureGate", _raise)
        expander, repo, _ = _build_expander(monkeypatch, _macro_batch())
        import asyncio

        skeletons = asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        assert len(skeletons) == 4
        assert len(repo.created_plots) == 4


class TestWarnContract:
    def test_warn_reports_but_saves_llm_output(self, monkeypatch):
        """warn で reporter に違反報告・DB は LLM 応答のまま保存されること。"""
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "warn")
        expander, repo, _ = _build_expander(monkeypatch, _macro_batch())
        reporter = _FakeReporter()
        import asyncio

        skeletons = asyncio.run(
            expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4], reporter=reporter)
        )
        # 骨子は変更されない
        assert [s.tension for s in skeletons] == [20, 95, 60, 60]
        # 違反 (20→95: Δ75 > 40) が報告される
        assert any("違反" in msg and "warning" == level for msg, level in reporter.messages)


class TestEnforceContract:
    def test_enforce_saves_corrected_tension(self, monkeypatch):
        """enforce で補正済み tension が DB 保存されること (実 balancer 経路)。"""
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "enforce")
        expander, repo, _ = _build_expander(monkeypatch, _macro_batch())
        import asyncio

        asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        saved_tensions = [plot.tension for _, _, plot in repo.created_plots]
        # 補正は tension のみで行われ、LLM 応答 (20,95,60,60) から変化していること
        assert saved_tensions != [20, 95, 60, 60]
        # P6: 補正後も tension 以外 (title / summary) は LLM 応答のまま
        assert [plot.title for _, _, plot in repo.created_plots] == [
            s.title for s in _macro_batch().episodes
        ]

    def test_enforce_correction_is_deterministic(self, monkeypatch):
        """同入力 → 同一の補正結果 (CP-SAT シングルワーカー契約 / P2)。"""
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "enforce")
        import asyncio

        expander_a, _, _ = _build_expander(monkeypatch, _macro_batch())
        expander_b, _, _ = _build_expander(monkeypatch, _macro_batch())
        skeletons_a = asyncio.run(expander_a.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        skeletons_b = asyncio.run(expander_b.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        assert [s.tension for s in skeletons_a] == [s.tension for s in skeletons_b]
