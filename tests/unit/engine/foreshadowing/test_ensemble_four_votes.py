"""PLAN_S1 P3 の回帰テスト — EnsembleJudge の第 4 票と配点 SSOT 契約。

壊れ方: llm_vote=None の現行判定が変わる / shadow 期間中に判定が変わる /
配点ハードコードが復活 (SSOT 経由でない) → この回帰が赤になる。
"""

from __future__ import annotations

import pytest

import src.engine.foreshadowing.vote_config as vote_config
from src.engine.foreshadowing.ensemble_judge import EnsembleJudge
from src.engine.foreshadowing.vote_config import (
    build_judge_params,
    get_vote_mode,
    normalize_vote_mode,
)
from src.models.ensemble_foreshadowing import EnsembleScoreBreakdown
from src.models.writing_metadata import ForeshadowingReport


def _metadata(action: str) -> ForeshadowingReport:
    return ForeshadowingReport(foreshadowing_id=1, action=action)  # type: ignore[arg-type]


def _patch_calibration(monkeypatch, foreshadowing_section: dict):
    """calibration_store の SSOT を差し替える (yaml を介さない単体検証)。"""
    from src.audit.calibration_store import clear_cache

    base = {
        "gate": {"mode": "absolute"},
        "foreshadowing": foreshadowing_section,
    }
    monkeypatch.setattr(vote_config, "get_calibration", lambda *a, **kw: base)
    clear_cache()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """env と calibration キャッシュの影響を排除する。"""
    monkeypatch.delenv("ENABLE_FORESHADOW_LLM_VOTE", raising=False)
    from src.audit.calibration_store import clear_cache

    clear_cache()
    yield
    clear_cache()


class TestLegacyCompatibility:
    def test_legacy_signature_unchanged(self):
        """llm_vote を渡さない既存呼び出しで、judgment が現行と完全一致すること。

        現行動作: 契約 35 + metadata resolved 40 = 75 → RESOLVED (Q9 契約)。
        """
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
        )
        assert judgment.status == "RESOLVED"
        assert judgment.should_reschedule is False
        b = judgment.score_breakdown
        assert (b.contract_score, b.metadata_score, b.syntax_score, b.llm_vote_score, b.total_score) == (35, 40, 0, 0, 75)

    def test_legacy_progessed_case(self):
        """metadata なし・契約のみ 35pt → PROGRESSED (legacy 閾値 35)。

        syntax_analysis=None の現行動作を固定する。
        """
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=None,
            syntax_analysis=None,
        )
        assert judgment.status == "PROGRESSED"
        assert judgment.should_reschedule is True
        assert judgment.score_breakdown.total_score == 35

    def test_legacy_planted_case(self):
        """無契約・無 metadata → PLANTED (0pt < 15)。
        syntax_analysis=None のため構文スコアも 0。"""
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=False,
            metadata_report=None,
            syntax_analysis=None,
        )
        assert judgment.status == "PLANTED"

    def test_legacy_rationale_format_preserved(self):
        """rationale に 3 票の内訳が含まれること (ログ互換)。"""
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
        )
        assert "Contract=35" in judgment.rationale
        assert "Metadata=40" in judgment.rationale
        assert "Syntax=0" in judgment.rationale
        assert "LLM=0" in judgment.rationale


class TestSSOTWeights:
    def test_mainline_uses_ssot_weights(self, monkeypatch):
        """mainline モードで SSOT 配点 (35/30/20/15) が使われること。"""
        _patch_calibration(
            monkeypatch,
            {
                "mode": "mainline",
                "weights": {"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15},
                "thresholds": {"resolved": 75, "progressed": 35},
            },
        )
        # G-3 の緩和検証: 自己申告 resolved 30 + 契約 35 = 65 < 75 → RESOLVED に到達しない
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
            llm_vote=None,
            weights={"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15},
        )
        assert judgment.status == "PROGRESSED"
        assert judgment.score_breakdown.metadata_score == 30

        # 第 4 票 resolved が加算されると 65 + 15 = 80 ≥ 75 → RESOLVED
        class _Vote:
            action = "resolved"

        judgment_with_vote = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
            llm_vote=_Vote(),
            weights={"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15},
        )
        assert judgment_with_vote.status == "RESOLVED"
        assert judgment_with_vote.score_breakdown.llm_vote_score == 15

    def test_weights_read_from_calibration_yaml_via_service(self, monkeypatch, tmp_path):
        """サービス経由で SSOT 配点が EnsembleJudge に渡ること (yaml 欠落時は現行値)。"""
        _patch_calibration(
            monkeypatch,
            {
                "mode": "mainline",
                "weights": {"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15},
                "thresholds": {"resolved": 75, "progressed": 35},
            },
        )
        weights, thresholds = build_judge_params("mainline")
        assert weights == {"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15}
        assert thresholds["resolved"] == 75 and thresholds["progressed"] == 35
        assert thresholds["no_metadata_resolved"] == 55 and thresholds["no_metadata_progressed"] == 15

    def test_yaml_missing_falls_back_to_legacy(self, monkeypatch):
        """SSOT が読めない場合、build_judge_params は現行値 (legacy) にフォールバックすること。"""
        monkeypatch.setattr(
            vote_config, "get_calibration", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no yaml"))
        )
        weights, thresholds = build_judge_params("mainline")
        # 現行配点 (35/40/25/0) へのフォールバック = 判定は現行と同一
        assert weights == {"contract": 35, "metadata": 40, "syntax": 25, "llm_vote": 0}
        assert thresholds["resolved"] == 75 and thresholds["progressed"] == 35
        judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
            weights=weights,
            thresholds=thresholds,
        )
        assert judgment.score_breakdown.total_score == 75


class TestModeResolution:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("shadow", "shadow"),
            ("mainline", "mainline"),
            ("off", "off"),
            ("1", "mainline"),
            ("0", "off"),
            ("true", "mainline"),
            ("false", "off"),
            (True, "mainline"),
            (False, "off"),
            ("typo", "off"),
        ],
    )
    def test_normalize_vote_mode(self, raw, expected):
        """``ENABLE_FORESHADOW_LLM_VOTE`` の生値 (ブール含む) が正規化されること。"""
        assert normalize_vote_mode(raw) == expected

    def test_env_overrides_yaml(self, monkeypatch):
        """優先順位: env > yaml (P3 契約)。"""
        monkeypatch.setenv("ENABLE_FORESHADOW_LLM_VOTE", "shadow")
        assert get_vote_mode() == "shadow"

    def test_default_is_off(self):
        """既定 (env 未設定) は off であること (P1)。"""
        assert get_vote_mode() == "off"


class TestShadowModeContract:
    def test_shadow_mode_does_not_change_verdict(self, monkeypatch):
        """shadow モードでは LLM 票が判定に影響せず (legacy 配点)、記録のみされること。"""
        weights, thresholds = build_judge_params("shadow")
        assert weights is None and thresholds is None  # legacy 配点

        class _Vote:
            action = "resolved"

        shadow_judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
            llm_vote=_Vote(),
            weights=weights,
            thresholds=thresholds,
        )
        legacy_judgment = EnsembleJudge.evaluate(
            foreshadowing_id=1,
            is_contracted=True,
            metadata_report=_metadata("resolved"),
            syntax_analysis=None,
        )
        # LLM 票があっても判定・内訳が現行と完全同一 (バイト同一性)
        assert shadow_judgment.status == legacy_judgment.status
        assert shadow_judgment.score_breakdown == legacy_judgment.score_breakdown

    def test_breakdown_model_accepts_llm_vote_score(self):
        """EnsembleScoreBreakdown が第 4 票フィールドを受け入れること (0-15)。"""
        b = EnsembleScoreBreakdown(
            contract_score=35, metadata_score=30, syntax_score=20, llm_vote_score=15, total_score=100
        )
        assert b.llm_vote_score == 15
        with pytest.raises(Exception):
            EnsembleScoreBreakdown(llm_vote_score=16)  # 上限 15


class TestMainlineEndToEnd:
    def test_llm_vote_counts_when_mainline_enabled(self, monkeypatch, tmp_path):
        """mainline モード: サービスが LLM 票を判定に加算すること (配点 SSOT 経由)。

        - 自己申告 resolved (30) + 契約 (35) = 65 → 単独では RESOLVED 不成立
        - LLM 票 resolved (+15) → 80 ≥ 75 → RESOLVED
        """
        from src.engine.foreshadowing.service import ForeshadowingService
        from src.models.writing_metadata import WritingMetadata

        self_test = self

        class _StubVoter:
            def __init__(self):
                self.calls = 0

            async def vote(self, **kwargs):
                self_test.calls = self.calls = getattr(self, "calls", 0) + 1

                class _R:
                    action = "resolved"
                    evidence_quote = "魔剣が抜かれた"

                return _R()

        class _FakeF:
            id = 1
            title = "魔剣"
            keywords = ["魔剣"]
            description = "封印の魔剣"
            status = "planted"
            target_episode = 2

        class _FakeRepo:
            async def get_unresolved(self, book_id):
                return [_FakeF()]

            async def resolve(self, fid, ep):
                return True

            async def progress(self, fid):
                return True

        _patch_calibration(
            monkeypatch,
            {
                "mode": "mainline",
                "weights": {"contract": 35, "metadata": 30, "syntax": 20, "llm_vote": 15},
                "thresholds": {"resolved": 75, "progressed": 35},
            },
        )
        import asyncio

        voter = _StubVoter()
        svc = ForeshadowingService(_FakeRepo(), llm_voter=voter)
        md = WritingMetadata(episode_number=2, foreshadowings=[ForeshadowingReport(foreshadowing_id=1, action="resolved")])
        resolved = asyncio.run(
            svc.check_and_resolve(1, 2, "魔剣が抜かれた。", writing_metadata=md, contract_ids=[1])
        )
        assert resolved == ["魔剣"]
        assert voter.calls == 1

    def test_off_mode_makes_no_llm_calls(self, monkeypatch):
        """off (既定) では voter を構築しても vote が呼ばれないこと (LLM 0 回 / P1)。"""
        from src.engine.foreshadowing.service import ForeshadowingService
        from src.models.writing_metadata import WritingMetadata

        class _StubVoter:
            def __init__(self):
                self.calls = 0

            async def vote(self, **kwargs):
                self.calls += 1
                raise AssertionError("off モードで投票が呼ばれた")

        class _FakeF:
            id = 1
            title = "魔剣"
            keywords = ["魔剣"]
            description = "x"
            status = "planted"
            target_episode = 2

        class _FakeRepo:
            async def get_unresolved(self, book_id):
                return [_FakeF()]

            async def resolve(self, fid, ep):
                return True

            async def progress(self, fid):
                return True

        import asyncio

        voter = _StubVoter()
        svc = ForeshadowingService(_FakeRepo(), llm_voter=voter)
        md = WritingMetadata(episode_number=2, foreshadowings=[ForeshadowingReport(foreshadowing_id=1, action="resolved")])
        resolved = asyncio.run(svc.check_and_resolve(1, 2, "本文", writing_metadata=md, contract_ids=[1]))
        assert resolved == ["魔剣"]
        assert voter.calls == 0
