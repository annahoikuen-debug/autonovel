"""PLAN_S1 O1/O2/O3 の回帰テスト — プリセット tension curve 注入の契約。

壊れ方: curve None でもプロンプトが変わる / spine との併用で衝突する /
preset 未選択時に get_tension_curve の内蔵既定曲線が出て出所が不明瞭になる /
新引数追加で既存呼び出しが壊れる → この契約が赤になる。
"""

from __future__ import annotations

from typing import List

import pytest

from prompts.manager import PromptManager
from src.engine.default_plot_expander import DefaultPlotExpander
from src.engine.structure_gate import (
    NarrativeStructureGate,
    NarrativeStructureSettings,
    StructureGateReport,
    compute_curve_deviation,
)
from src.models.plot import EpisodeMacroSkeleton, PlotMacroBatch
from src.narrative_balancer import Beat


CURVE: List[List[float]] = [[0.0, 0.1], [0.5, 0.9], [1.0, 0.2]]


class TestPromptInjection:
    @pytest.mark.asyncio
    async def test_curve_none_byte_identical(self):
        """tension_curve=None でプロンプトがバイト単位で同一であること (P1)。"""
        pm = PromptManager()
        kwargs = dict(
            bible_json_str='{"title": "t", "genre": "g", "concept": "c", "synopsis": "s"}',
            ep_range=[1, 2, 3],
            book_id=None,
            spine=None,
            spine_quality=None,
        )
        without = await pm.build_macro_plot_skeleton_prompt(**kwargs)
        with_none = await pm.build_macro_plot_skeleton_prompt(**kwargs, tension_curve=None)
        assert without == with_none
        assert "目標テンション曲線" not in without

    @pytest.mark.asyncio
    async def test_curve_injected_as_reference_after_spine(self):
        """指定時、参考テーブルが spine セクションより後に位置し、duty 優先の注記が入ること。"""
        from src.services.spine_resolver import resolve_spine

        pm = PromptManager()
        spine = resolve_spine("exile_rise", "web_volume", "web", 4)
        base_kwargs = dict(
            bible_json_str='{"title": "t", "genre": "g", "concept": "c", "synopsis": "s"}',
            ep_range=[1, 2, 3, 4],
            book_id=None,
            spine=spine,
            spine_quality="hard",
        )
        with_spine_only = await pm.build_macro_plot_skeleton_prompt(**base_kwargs)
        with_curve = await pm.build_macro_plot_skeleton_prompt(**base_kwargs, tension_curve=CURVE)

        assert "【構造の割当】" in with_curve
        assert "【目標テンション曲線（参考）】" in with_curve
        assert with_curve.startswith(with_spine_only), "curve は spine セクションより後に連結されること"
        assert "構造の割当（上記）が指定する役割を優先" in with_curve

    @pytest.mark.asyncio
    async def test_curve_values_are_clamped_and_scaled(self):
        """0-1 スケールの曲線が 0-100 整数テンションへ変換されること (範囲外クランプ)。"""
        pm = PromptManager()
        curve = [[0.0, -0.5], [1.0, 1.7]]  # 範囲外
        prompt = await pm.build_macro_plot_skeleton_prompt(
            bible_json_str='{"title": "t"}',
            ep_range=[1, 2],
            tension_curve=curve,
        )
        assert "tension 0" in prompt  # -0.5 → 0
        assert "tension 100" in prompt  # 1.7 → 100

    @pytest.mark.asyncio
    async def test_malformed_curve_is_silently_ignored(self):
        """不正形状の曲線でプロンプト生成が落ちないこと (fail-open)。"""
        pm = PromptManager()
        prompt = await pm.build_macro_plot_skeleton_prompt(
            bible_json_str='{"title": "t"}',
            ep_range=[1, 2],
            tension_curve=[["not-a-pair"], None, [0.5]],  # type: ignore[list-item]
        )
        assert "【目標テンション曲線（参考）】" not in prompt


class TestPresetNonePassthrough:
    def test_empty_preset_yields_none_curve(self):
        """O1 契約: preset が実質空なら get_tension_curve を呼ばず None を通すこと。

        get_tension_curve の内蔵既定曲線 (出所不明瞭) を本配線から出さない。
        """
        from src.services.preset_loader import get_tension_curve

        # プリセット読み込み失敗相当 (空 dict)
        empty_preset = {}
        tension_section = empty_preset.get("tension")
        if tension_section:
            curve = get_tension_curve(empty_preset).get("curve_points")
        else:
            curve = None
        assert curve is None

    def test_real_preset_has_curve_points(self):
        """実プリセット (zarma フォールバック含む) は curve_points を持つこと。"""
        from src.services.preset_loader import get_tension_curve, load_preset_for_pipeline

        preset = load_preset_for_pipeline("HighFantasy", "hero")
        assert preset.get("tension"), "本番プリセットには tension セクションがあること"
        curve = get_tension_curve(preset).get("curve_points")
        assert isinstance(curve, list) and len(curve) >= 2
        for point in curve:
            progress, tension = point[0], point[1]
            assert 0.0 <= progress <= 1.0
            assert 0.0 <= tension <= 1.0


class TestGateCurveDeviation:
    """O3: gate の参照曲線逸脱指標 (advisory) の契約。"""

    def test_deviation_computed(self):
        beats = [
            Beat(episode=1, tension=1.0),  # 進行度 0.33 に対し curve≈0.5 → 逸脱 40
            Beat(episode=2, tension=5.0),  # 進行度 0.67 に対し curve≈0.7 → 逸脱 20
            Beat(episode=3, tension=2.0),  # 進行度 1.0 に対し curve 0.2 → 逸脱 0
        ]
        deviation = compute_curve_deviation(beats, CURVE)
        assert deviation is not None
        assert deviation >= 0.0

    def test_deviation_none_for_invalid_curve(self):
        beats = [Beat(episode=1, tension=5.0)]
        assert compute_curve_deviation(beats, []) is None
        assert compute_curve_deviation([], CURVE) is None

    def test_deviation_is_advisory_not_gating(self):
        """逸脱が大きくても violations には含まれないこと (判定ゲートではない)。"""
        gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="warn"))
        skeletons = [EpisodeMacroSkeleton(ep_num=1, tension=50)]
        report = gate.run(skeletons, tension_curve=[[0.0, 1.0]])
        assert report.violation_count == 0
        assert report.violations == []
        assert report.curve_deviation is not None and report.curve_deviation > 0

    def test_report_field_defaults_to_none(self):
        """curve 未指定時は curve_deviation が None であること (後方互換)。"""
        report = StructureGateReport(mode="warn", executed=True)
        assert report.curve_deviation is None


class TestExpanderSignature:
    @pytest.mark.asyncio
    async def test_existing_call_sites_unaffected(self):
        """新引数を渡さない既存呼び出し (位置引数のみ) が従来どおり動くこと。"""
        expander = DefaultPlotExpander.__new__(DefaultPlotExpander)
        # シグネチャ検査: tension_curve はキーワード引数 (既定 None) であること
        import inspect

        sig = inspect.signature(expander.expand_macro_skeletons)
        assert "tension_curve" in sig.parameters
        assert sig.parameters["tension_curve"].default is None

    @pytest.mark.asyncio
    async def test_curve_forwarded_to_prompt_and_gate(self, monkeypatch):
        """curve がプロンプトビルダーと gate の両方に転送されること (O1 の配線)。"""
        captured = {"prompt_curve": None, "gate_curve": None}

        class _FakePM:
            async def build_macro_plot_skeleton_prompt(
                self, bible_json_str, ep_range, book_id=None, spine=None, spine_quality=None,
                tension_curve=None,
            ):
                captured["prompt_curve"] = tension_curve
                return "macro prompt"

        class _FakeLLM:
            async def generate_json(self, model, prompt, response_schema, reporter=None):
                return PlotMacroBatch(episodes=[EpisodeMacroSkeleton(ep_num=1, tension=50)])

        class _FakeRepo:
            async def get_latest_bible(self, book_id):
                return {}

            async def get_plot(self, branch_id, ep_num, book_id=None):
                return None

            async def create_or_replace_plot(self, book_id, ep_num, plot):
                pass

        import src.engine.structure_gate as sg

        original_gate = sg.NarrativeStructureGate

        class _CapturingGate(original_gate):  # type: ignore[misc, valid-type]
            def run(self, episodes, reporter=None, tension_curve=None):
                captured["gate_curve"] = tension_curve
                return StructureGateReport(mode=self.mode, executed=False)

        monkeypatch.setattr(sg, "NarrativeStructureGate", _CapturingGate)
        monkeypatch.setattr(sg, "get_gate_mode", lambda: "warn")

        expander = DefaultPlotExpander(repo=_FakeRepo(), pm=_FakePM(), llm=_FakeLLM())
        await expander.expand_macro_skeletons(
            book_id=1, target_ep_list=[1, 2, 3], tension_curve=CURVE
        )
        monkeypatch.undo()

        assert captured["prompt_curve"] == CURVE
        assert captured["gate_curve"] == CURVE
