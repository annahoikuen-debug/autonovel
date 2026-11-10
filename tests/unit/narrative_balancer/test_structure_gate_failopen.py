"""PLAN_S1 P3 (fail-open) の回帰テスト — gate がいかなる失敗でも執筆を止めないこと。

壊れ方: gate の例外で expand_macro_skeletons が落ちる /
ortools 欠落環境で macro 生成が失敗する / 不完全な balancer 出力で KeyError → 赤。
"""

from __future__ import annotations

from typing import List


from src.engine.structure_gate import (
    NarrativeStructureGate,
    NarrativeStructureSettings,
)
from src.models.plot import EpisodeMacroSkeleton
from src.narrative_balancer import IntegratedResult


def _skeleton(ep: int, tension: int, phase: str = "Friction") -> EpisodeMacroSkeleton:
    return EpisodeMacroSkeleton(ep_num=ep, tension=tension, current_chain_phase=phase)


def _violating_batch() -> List[EpisodeMacroSkeleton]:
    return [_skeleton(1, 20), _skeleton(2, 95), _skeleton(3, 60), _skeleton(4, 60)]


class _ExplodingBalancer:
    """orchestrate が常に例外を投げるスタブ。"""

    def orchestrate(self, state_input):
        raise RuntimeError("boom from balancer")


class _EmptyResultBalancer:
    """空の balanced_beats を返すスタブ。"""

    def orchestrate(self, state_input):
        return IntegratedResult(balanced_beats=[])


class _MalformedResultBalancer:
    """属性欠損のオブジェクトを返すスタブ。"""

    def orchestrate(self, state_input):
        return object()  # .balanced_beats が無い


class TestFailOpen:
    def test_orchestrate_exception_falls_back_to_off_behavior(self):
        """balancer が例外を投げても gate は骨子を変更せず正常に返ること。"""
        skeletons = _violating_batch()
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"),
            balancer=_ExplodingBalancer(),  # type: ignore[arg-type]
        )
        report = gate.run(skeletons)
        assert report.executed is False
        assert report.error is not None
        assert report.corrected_episode_count == 0
        # 骨子は off 挙動と同一 (未変更)
        assert [s.tension for s in skeletons] == [20, 95, 60, 60]

    def test_orchestrator_exception_propagates_nothing_to_caller(self):
        """例外が gate 外へ漏れないこと (run は常に StructureGateReport を返す)。"""
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="warn"),
            balancer=_ExplodingBalancer(),  # type: ignore[arg-type]
        )
        report = gate.run(_violating_batch())  # warn は balancer を呼ばないが、例外経路を踏む
        assert isinstance(report, type(gate.run(_violating_batch())))

    def test_missing_ortools_degrades_gracefully(self, monkeypatch):
        """ortools 欠落相当 (build_batch_balancer の ImportError) で執筆が継続すること。"""
        import src.engine.structure_gate as sg

        def _raise_import_error(n_episodes: int):
            raise ImportError("No module named 'ortools'")

        monkeypatch.setattr(sg, "build_batch_balancer", _raise_import_error)
        gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="enforce"))
        report = gate.run(_violating_batch())
        assert report.executed is False
        assert "ortools" in (report.error or "")

    def test_empty_balanced_beats_is_tolerated(self):
        """balanced_beats が空でも KeyError にならず、補正 0 件で返ること。"""
        skeletons = _violating_batch()
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"),
            balancer=_EmptyResultBalancer(),  # type: ignore[arg-type]
        )
        report = gate.run(skeletons)
        assert report.corrected_episode_count == 0
        assert report.error == "balancer returned no beats"
        assert [s.tension for s in skeletons] == [20, 95, 60, 60]

    def test_malformed_result_is_tolerated(self):
        """IntegratedResult 以外の戻り値でも落とさないこと。"""
        skeletons = _violating_batch()
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"),
            balancer=_MalformedResultBalancer(),  # type: ignore[arg-type]
        )
        report = gate.run(skeletons)
        assert report.corrected_episode_count == 0

    def test_reporter_failure_does_not_stop_gate(self):
        """reporter.report が例外を投げても gate は正常完了すること。"""

        class _BrokenReporter:
            def report(self, message: str, level: str = "info"):
                raise RuntimeError("reporter is broken")

        gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="warn"))
        report = gate.run(_violating_batch(), reporter=_BrokenReporter())
        assert report.executed is True
        assert report.violation_count >= 1

    def test_settings_load_failure_uses_defaults(self, monkeypatch, tmp_path):
        """yaml が読めない場合もデフォルト設定で継続すること (fail-open)。"""
        broken = tmp_path / "broken.yaml"
        broken.write_text("mode: [unclosed", encoding="utf-8")
        settings = sg_load(broken)
        assert settings.mode == "off"
        assert settings.max_step_delta == 4.0


def sg_load(path):
    from src.engine.structure_gate import load_settings

    return load_settings(config_path=str(path))
