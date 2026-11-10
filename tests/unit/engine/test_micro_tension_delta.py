"""PLAN_S1 N4 の回帰テスト — micro 経路の tension_delta 補正指示。

壊れ方: off でもプロンプトに補正指示が混入 / 閾値を超えても指示が出ない /
直前話が存在しない (第1話) 場合に落ちる → この回帰が赤になる。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import List

import pytest

from src.engine.default_plot_expander import DefaultPlotExpander
from src.models.plot import EpisodeMacroSkeleton, PlotMicroBlueprint


def _skeleton(ep: int, tension: int) -> EpisodeMacroSkeleton:
    return EpisodeMacroSkeleton(ep_num=ep, tension=tension)


class _FakeRepo:
    def __init__(self, prev_tension: int | None = None):
        self.prev_tension = prev_tension

    async def get_latest_bible(self, book_id):
        return {}

    async def get_all_characters(self, book_id):
        return []

    async def get_plot(self, branch_id, ep_num, book_id=None):
        if self.prev_tension is not None:
            return SimpleNamespace(tension=self.prev_tension)
        return None

    async def create_or_replace_plot(self, book_id, ep_num, plot):
        pass


class _PromptCapturingLLM:
    def __init__(self, ep_num: int = 1):
        self.ep_num = ep_num
        self.prompts: List[str] = []

    async def generate_json(self, model, prompt, response_schema, reporter=None):
        self.prompts.append(prompt)
        return PlotMicroBlueprint(ep_num=self.ep_num)


class _FakePM:
    async def build_micro_scene_expander_prompt(
        self, macro_skeleton, previous_ending_text="", characters_summary="",
        book_id=None, spine=None, spine_quality=None,
    ):
        return "micro prompt"


class _FakeReporter:
    def report(self, msg, level="info"):
        pass


DIRECTIVE_MARK = "【テンション補正指示】"


@pytest.fixture(autouse=True)
def _reset_gate_cache():
    from src.engine.structure_gate import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


def _run(monkeypatch, mode: str, prev_tension: int | None, skeleton_tension: int):
    monkeypatch.setenv("NARRATIVE_STRUCTURE_GATE", mode)
    repo = _FakeRepo(prev_tension=prev_tension)
    llm = _PromptCapturingLLM(ep_num=2)
    expander = DefaultPlotExpander(repo=repo, pm=_FakePM(), llm=llm)
    asyncio.run(
        expander.expand_single_micro(
            book_id=1, ep_num=2, skeleton=_skeleton(2, skeleton_tension), reporter=_FakeReporter()
        )
    )
    assert len(llm.prompts) == 1
    return llm.prompts[0]


class TestOffContract:
    def test_off_byte_identical_micro_prompt(self, monkeypatch):
        """off (既定) でプロンプトがバイト単位で同一であること (P1)。"""
        prompt = _run(monkeypatch, "off", prev_tension=90, skeleton_tension=10)
        assert prompt == "micro prompt"
        assert DIRECTIVE_MARK not in prompt

    def test_env_unset_is_off(self, monkeypatch):
        """env 未設定 = off であること。"""
        monkeypatch.delenv("NARRATIVE_STRUCTURE_GATE", raising=False)
        prompt = _run(monkeypatch, "off", prev_tension=90, skeleton_tension=10)
        assert DIRECTIVE_MARK not in prompt


class TestWarnDirective:
    def test_warn_injects_delta_directive_on_violation(self, monkeypatch):
        """直前 tension 90 → 本話 10 (Δ80 > 40) のとき指示が入ること。"""
        prompt = _run(monkeypatch, "warn", prev_tension=90, skeleton_tension=10)
        assert DIRECTIVE_MARK in prompt
        assert "90" in prompt and "10" in prompt

    def test_no_directive_within_budget(self, monkeypatch):
        """Δ40 以内では指示が入らないこと (過剰指示の防止)。"""
        prompt = _run(monkeypatch, "warn", prev_tension=90, skeleton_tension=60)
        assert DIRECTIVE_MARK not in prompt

    def test_no_directive_when_prev_plot_missing(self, monkeypatch):
        """直前話が存在しない (第1話相当) 場合は指示なしで正常動作すること。"""
        prompt = _run(monkeypatch, "warn", prev_tension=None, skeleton_tension=10)
        assert DIRECTIVE_MARK not in prompt

    def test_enforce_also_injects_directive(self, monkeypatch):
        """enforce でも micro プロンプトには指示注入を行うこと (enforce の無理やりな
        数値固定ではなく設計段階での緩和を優先 / N4 契約)。"""
        prompt = _run(monkeypatch, "enforce", prev_tension=90, skeleton_tension=10)
        assert DIRECTIVE_MARK in prompt


class TestDirectiveContent:
    def test_directive_contains_both_tensions_and_limit(self, monkeypatch):
        """指示文に直前・本話テンションと許容差が含まれること。"""
        prompt = _run(monkeypatch, "warn", prev_tension=90, skeleton_tension=10)
        assert "90" in prompt and "10" in prompt and "40" in prompt
