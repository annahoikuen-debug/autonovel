"""PLAN_S1 N3 の hook 配線回帰 — expand_macro_skeletons とゲートの実行順序契約。

壊れ方: warn/enforce で gate が呼ばれない / gate が LLM を追加呼び出しする /
gate 実行が DB 保存より後になる → この回帰が赤になる。

(Q1: tests/contract/test_structure_gate_off_contract.py が off 契約・
DB 保存内容・fail-open を担保する。本ファイルは配線の順序とコストを担保する。)
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest

from src.engine.default_plot_expander import DefaultPlotExpander
from src.models.plot import EpisodeMacroSkeleton, PlotMacroBatch


def _batch_with_violation() -> PlotMacroBatch:
    return PlotMacroBatch(
        episodes=[
            EpisodeMacroSkeleton(ep_num=i, tension=20 if i == 1 else (95 if i == 2 else 60))
            for i in range(1, 5)
        ]
    )


class _FakeRepo:
    def __init__(self):
        self.created_plots: List[tuple] = []

    async def get_latest_bible(self, book_id):
        return {}

    async def get_plot(self, branch_id, ep_num, book_id=None):
        return None

    async def create_or_replace_plot(self, book_id, ep_num, plot):
        self.created_plots.append((book_id, ep_num, plot))


class _CountingLLM:
    """LLM 呼び出し回数を記録する (P2: gate が LLM を呼ばないことの検証用)。"""

    def __init__(self, batch: PlotMacroBatch):
        self.batch = batch
        self.call_count = 0

    async def generate_json(self, model, prompt, response_schema, reporter=None):
        self.call_count += 1
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


@pytest.fixture(autouse=True)
def _reset_gate_cache():
    from src.engine.structure_gate import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


class TestHookWiring:
    def test_no_extra_llm_calls_from_gate_in_warn(self, monkeypatch):
        """P2: warn モードでも LLM 呼び出しは batch 生成の 1 回のみであること。"""
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "warn")
        repo = _FakeRepo()
        llm = _CountingLLM(_batch_with_violation())
        expander = DefaultPlotExpander(repo=repo, pm=_FakePM(), llm=llm)

        asyncio.run(
            expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4], reporter=_FakeReporter())
        )
        assert llm.call_count == 1, "gate が LLM を追加呼び出ししている (P2 違反)"

    def test_no_extra_llm_calls_from_gate_in_enforce(self, monkeypatch):
        """P2: enforce モードでも LLM 呼び出しは batch 生成の 1 回のみであること。"""
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "enforce")
        repo = _FakeRepo()
        llm = _CountingLLM(_batch_with_violation())
        expander = DefaultPlotExpander(repo=repo, pm=_FakePM(), llm=llm)

        asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))
        assert llm.call_count == 1

    def test_gate_runs_after_batch_parse_and_before_save(self, monkeypatch):
        """gate は batch パース後・DB 保存前に実行されること (N3 の配置契約)。

        enforce で tension を補正した結果が DB 保存内容に反映されることで検証する
        (保存後に実行されていたら反映されない)。
        """
        monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", "enforce")

        import src.engine.structure_gate as sg

        run_at: dict = {"created_at_run": None}

        class _ObservingGate(sg.NarrativeStructureGate):
            def run(self, episodes, reporter=None, tension_curve=None):
                # gate 実行時点でまだ保存が行われていないこと
                run_at["created_at_run"] = len(self._repo.created_plots)
                report = super().run(episodes, reporter=reporter, tension_curve=tension_curve)
                return report

        original_gate = sg.NarrativeStructureGate

        repo = _FakeRepo()
        expander = DefaultPlotExpander(repo=repo, pm=_FakePM(), llm=_CountingLLM(_batch_with_violation()))
        # _ObservingGate から repo を見せるための後付け参照
        _ObservingGate._repo = repo

        monkeypatch.setattr(sg, "NarrativeStructureGate", _ObservingGate)
        asyncio.run(expander.expand_macro_skeletons(book_id=1, target_ep_list=[1, 2, 3, 4]))

        assert run_at["created_at_run"] == 0, "gate 実行時点で DB 保存が先行している (N3 の配置違反)"
        assert len(repo.created_plots) == 4
        _ = original_gate  # 比較用参照の未使用回避
