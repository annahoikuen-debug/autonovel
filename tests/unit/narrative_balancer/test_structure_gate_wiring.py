"""PLAN_S1 N2 の回帰テスト — BeatMapper と NarrativeStructureGate の配線単体。

壊れ方: 0-100 ↔ 0-10 の換算ずれ / クランプ漏れ / 決定論崩れ /
enforce が tension 以外の物語設計フィールドを書き換える → このテストが赤になる。
"""

from __future__ import annotations

import copy
from typing import List, Optional

import pytest

from src.engine.structure_gate import (
    BeatMapper,
    NarrativeStructureGate,
    NarrativeStructureSettings,
    convert_tension,
    detect_tension_violations,
    load_settings,
)
from src.models.plot import EpisodeMacroSkeleton
from src.narrative_balancer import Beat


def _skeleton(ep: int, tension: int, phase: str = "Friction", **kwargs) -> EpisodeMacroSkeleton:
    return EpisodeMacroSkeleton(ep_num=ep, tension=tension, current_chain_phase=phase, **kwargs)


class TestConvertTension:
    """0-100 → 0-10 換算の契約 (Q2)。"""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (100, 10.0),
            (55, 5.5),
            (0, 0.0),
            (150, 10.0),  # 範囲外クランプ
            (-5, 0.0),  # 範囲外クランプ
            (None, None),
            (float("nan"), None),
            (float("inf"), None),
            ("abc", None),
            ("72", 7.2),  # 文字列数値の救済
        ],
    )
    def test_conversion_table(self, raw, expected: Optional[float]):
        assert convert_tension(raw) == expected

    def test_default_is_not_used_for_missing(self):
        """欠損は None (Beat 契約) であり、default_tension を埋め込まないこと。"""
        assert convert_tension(None, default=5.0) is None


class TestBeatMapper:
    def test_scale_conversion_in_beats(self):
        mapper = BeatMapper()
        beats = mapper.to_beats([_skeleton(1, 100), _skeleton(2, 55), _skeleton(3, 0)])
        assert [b.tension for b in beats] == [10.0, 5.5, 0.0]

    def test_sorts_by_ep_num_and_renumbers(self):
        """ep_num で安定ソートし、1..N に再採番すること (applier 前提の契約)。"""
        mapper = BeatMapper()
        beats = mapper.to_beats([_skeleton(3, 50), _skeleton(1, 50), _skeleton(2, 50)])
        assert [b.episode for b in beats] == [1, 2, 3]

    def test_missing_tension_becomes_none(self):
        """欠損 tension は Beat.tension=None で落ちないこと (Q2 契約)。"""
        mapper = BeatMapper()
        skeleton = EpisodeMacroSkeleton(ep_num=1)  # tension デフォルト 50
        beat = mapper.to_beats([skeleton])[0]
        assert beat.tension == 5.0  # 50/10
        # 生値 None は convert_tension で None
        assert convert_tension(None) is None

    def test_chain_phase_mapping(self):
        """normalize_chain_phase 語彙 → BeatType の対応 (SSOT マッピング)。"""
        mapper = BeatMapper()
        beats = mapper.to_beats(
            [
                _skeleton(1, 50, "Friction"),
                _skeleton(2, 50, "Prep"),
                _skeleton(3, 50, "Hate"),
                _skeleton(4, 50, "Payoff"),
                _skeleton(5, 50, "Fulfillment"),
            ]
        )
        assert [b.beat_type.value for b in beats] == [
            "SETUP",
            "RISING",
            "DISASTER",
            "PAYOFF",
            "RESOLUTION",
        ]

    def test_unknown_phase_falls_back_to_setup(self):
        """未知フェーズは SETUP にフォールバックすること (SSOT 注記の契約)。"""
        mapper = BeatMapper()
        beats = mapper.to_beats([_skeleton(1, 50, "UnknownPhase")])
        assert beats[0].beat_type.value == "SETUP"

    def test_story_design_fields_copied(self):
        """title / summary / foreshadowing が Beat へコピーされること。"""
        mapper = BeatMapper()
        skeleton = _skeleton(
            1,
            50,
            title="旅立ち",
            one_line_summary="村を出る",
            foreshadowing_plan=["F1", "F2"],
        )
        beat = mapper.to_beats([skeleton])[0]
        assert beat.title == "旅立ち"
        assert beat.summary == "村を出る"
        assert beat.foreshadowing_setup == ["F1", "F2"]
        assert beat.characters == []
        assert beat.is_defeat is False

    def test_apply_tension_back_writes_int(self):
        """enforce 用の書き戻し: ×10 復元・int・クランプ。"""
        mapper = BeatMapper()
        skeletons = [_skeleton(1, 20), _skeleton(2, 95)]
        beats = [
            Beat(episode=1, tension=4.6),  # → 46
            Beat(episode=2, tension=12.0),  # → 100 (クランプ)
        ]
        changed = mapper.apply_tension_back(skeletons, beats)
        assert changed == 2
        assert [s.tension for s in skeletons] == [46, 100]
        assert all(isinstance(s.tension, int) for s in skeletons)


class TestDetectTensionViolations:
    def _settings(self, delta: float = 4.0, rolling: float = 6.0) -> NarrativeStructureSettings:
        return NarrativeStructureSettings(max_step_delta=delta, rolling_min_sum=rolling)

    def test_detects_step_delta_violation(self):
        beats = [Beat(episode=1, tension=2.0), Beat(episode=2, tension=6.1)]
        violations = detect_tension_violations(beats, self._settings())
        assert len(violations) == 1
        assert "ep 1" in violations[0] and "ep 2" in violations[0]

    def test_detects_rolling_sum_violation(self):
        beats = [Beat(episode=1, tension=1.0), Beat(episode=2, tension=1.0), Beat(episode=3, tension=1.0)]
        violations = detect_tension_violations(beats, self._settings())
        assert any("rolling" in v for v in violations)

    def test_clean_sequence_has_no_violations(self):
        beats = [
            Beat(episode=1, tension=2.0),
            Beat(episode=2, tension=5.0),
            Beat(episode=3, tension=8.0),
            Beat(episode=4, tension=5.0),
        ]
        assert detect_tension_violations(beats, self._settings()) == []

    def test_none_tension_episodes_are_skipped(self):
        """tension 欠損話は両制約の判定から除外されること (docstring 契約)。"""
        beats = [
            Beat(episode=1, tension=2.0),
            Beat(episode=2, tension=None),
            Beat(episode=3, tension=2.0),
        ]
        assert detect_tension_violations(beats, self._settings()) == []

    def test_constants_come_from_settings(self):
        """SSOT 定数を参照していること (max_step_delta を変えると判定が変わる)。"""
        beats = [Beat(episode=1, tension=2.0), Beat(episode=2, tension=6.5)]
        strict = detect_tension_violations(beats, self._settings(delta=4.0))
        loose = detect_tension_violations(beats, self._settings(delta=5.0))
        assert len(strict) == 1
        assert loose == []


class _StubBalancer:
    """orchestrate の挙動を固定するスタブ (LLM 0 回・決定論検証用)。"""

    def __init__(self, tensions: Optional[List[Optional[float]]] = None, raise_error: Optional[Exception] = None):
        self.tensions = tensions
        self.raise_error = raise_error
        self.calls = 0

    def orchestrate(self, state_input):
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        from src.narrative_balancer import IntegratedResult

        beats = [b.model_copy(deep=True) for b in state_input.beats]
        if self.tensions is not None:
            for beat, tension in zip(beats, self.tensions):
                beat.tension = tension
        return IntegratedResult(balanced_beats=beats)


class TestGateEnforce:
    def test_enforce_only_touches_tension(self):
        """P6: enforce 補正後も tension 以外の骨子フィールドが不変であること。"""
        skeletons = [
            _skeleton(1, 20, title="A", one_line_summary="s1", foreshadowing_plan=["F1"]),
            _skeleton(2, 95, phase="Hate", title="B", one_line_summary="s2"),
            _skeleton(3, 60, phase="Payoff", title="C", one_line_summary="s3"),
            _skeleton(4, 60, phase="Fulfillment", title="D", one_line_summary="s4"),
        ]
        before = [s.model_dump() for s in skeletons]
        balancer = _StubBalancer(tensions=[4.0, 8.0, 6.0, 6.0])
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"), balancer=balancer  # type: ignore[arg-type]
        )
        report = gate.run(skeletons)

        assert report.mode == "enforce"
        assert report.corrected_episode_count == 2
        assert [s.tension for s in skeletons] == [40, 80, 60, 60]
        after = [s.model_dump() for s in skeletons]
        for old, new in zip(before, after):
            old.pop("tension")
            new.pop("tension")
        assert old == new or all(a == b for a, b in zip(before, after))

    def test_enforce_skips_balancer_when_no_violations(self):
        """違反ゼロなら orchestrate を呼ばないこと (コスト最小化の契約)。"""
        skeletons = [_skeleton(i, 50) for i in range(1, 5)]
        balancer = _StubBalancer()
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"), balancer=balancer  # type: ignore[arg-type]
        )
        report = gate.run(skeletons)
        assert balancer.calls == 0
        assert report.corrected_episode_count == 0

    def test_gate_is_deterministic_with_stub(self):
        """同入力 → 同出力 (スタブ balancer で 2 回)。"""
        skeletons_a = [_skeleton(1, 20), _skeleton(2, 95), _skeleton(3, 60), _skeleton(4, 60)]
        skeletons_b = copy.deepcopy(skeletons_a)
        balancer = _StubBalancer(tensions=[4.0, 8.0, 6.0, 6.0])
        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="enforce"), balancer=balancer  # type: ignore[arg-type]
        )
        gate.run(skeletons_a)
        gate.run(skeletons_b)
        assert [s.tension for s in skeletons_a] == [s.tension for s in skeletons_b]

    def test_gate_makes_no_llm_calls(self):
        """P2: gate 実行中に LLM 呼び出しが発生しないこと。"""
        calls: List[tuple] = []

        class _Recorder:
            def __getattr__(self, name):
                def _record(*args, **kwargs):
                    calls.append((name, args, kwargs))

                return _record

        import src.engine.structure_gate as sg

        original = sg.GlobalNarrativeBalancer
        sentinel = _Recorder()

        class _Watcher(original):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                sentinel.__getattr__("instantiated")()

        sg.GlobalNarrativeBalancer = _Watcher
        try:
            skeletons = [_skeleton(1, 20), _skeleton(2, 95), _skeleton(3, 60), _skeleton(4, 60)]
            gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="warn"))
            gate.run(skeletons)
        finally:
            sg.GlobalNarrativeBalancer = original
        # warn モードでは balancer を構築しない (検出のみ)
        assert not hasattr(sentinel, "instantiated") or calls == []


class TestGateOffAndWarn:
    def test_off_mode_noop(self):
        """off では実行されず、骨子を一切変更しないこと (P1)。"""
        skeletons = [_skeleton(1, 20), _skeleton(2, 95)]
        gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="off"))
        report = gate.run(skeletons)
        assert report.executed is False
        assert [s.tension for s in skeletons] == [20, 95]

    def test_should_run_contract(self):
        """should_run(): off で False、それ以外で True (呼び出しコストゼロ契約)。"""
        assert NarrativeStructureGate(settings=NarrativeStructureSettings(mode="off")).should_run() is False
        assert NarrativeStructureGate(settings=NarrativeStructureSettings(mode="warn")).should_run() is True

    def test_warn_reports_without_modifying(self):
        """warn で違反報告のみ・骨子不変であること。"""
        skeletons = [_skeleton(1, 20), _skeleton(2, 95), _skeleton(3, 60), _skeleton(4, 60)]
        messages: List[str] = []

        class _Reporter:
            def report(self, message: str, level: str = "info"):
                messages.append(message)

        gate = NarrativeStructureGate(
            settings=NarrativeStructureSettings(mode="warn"), balancer=_StubBalancer()  # type: ignore[arg-type]
        )
        report = gate.run(skeletons, reporter=_Reporter())
        assert report.mode == "warn"
        assert report.violation_count >= 1
        assert [s.tension for s in skeletons] == [20, 95, 60, 60]
        assert any("違反" in m for m in messages)

    def test_empty_episodes_is_noop(self):
        """空骨子列でも落ちないこと。"""
        gate = NarrativeStructureGate(settings=NarrativeStructureSettings(mode="enforce"))
        report = gate.run([])
        assert report.executed is False

    def test_settings_loaded_from_repo_yaml(self):
        """リポジトリの SSOT yaml が読み込まれ、既定 mode が off であること。"""
        settings = load_settings()
        assert settings.mode == "off"
        assert settings.max_step_delta == 4.0
        assert settings.rolling_min_sum == 6.0
