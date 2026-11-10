"""PLAN_S1 P4 の回帰テスト — 伏線 LLM 投票の shadow 記録と分析 CLI。

壊れ方: shadow 記録が本線判定を変える / 空ログで分析 CLI が例外 /
記録の失敗で回収処理が止まる → この回帰が赤になる。
"""

from __future__ import annotations

import asyncio
import json

import pytest

import src.engine.foreshadowing.vote_config as vote_config
from src.engine.foreshadowing.service import ForeshadowingService
from src.engine.foreshadowing.vote_shadow import analyze_shadow_log, record_vote_shadow
from src.models.writing_metadata import ForeshadowingReport, WritingMetadata


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ENABLE_FORESHADOW_LLM_VOTE", raising=False)
    from src.audit.calibration_store import clear_cache

    clear_cache()
    yield
    clear_cache()


class TestRecordAndAnalyze:
    def test_record_writes_jsonl(self, tmp_path):
        """shadow 記録が JSONL に書かれること。"""
        log_path = tmp_path / "shadow.jsonl"
        ok = record_vote_shadow(
            book_id=1,
            episode_num=3,
            foreshadowing_id=10,
            foreshadowing_title="魔剣",
            llm_action="resolved",
            judgment_status="RESOLVED",
            output_path=log_path,
        )
        assert ok is True
        data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert data["foreshadowing_id"] == 10
        assert data["llm_action"] == "resolved"
        assert data["judgment_status"] == "RESOLVED"
        assert data["agree"] is True

    def test_disagreement_recorded(self, tmp_path):
        """LLM 票と本線判定の不一致が agree=False で記録されること。"""
        log_path = tmp_path / "shadow.jsonl"
        record_vote_shadow(
            book_id=1, episode_num=3, foreshadowing_id=10, foreshadowing_title="魔剣",
            llm_action="unmentioned", judgment_status="RESOLVED", metadata_action="resolved",
            output_path=log_path,
        )
        data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert data["agree"] is False
        assert data["metadata_over_report"] is True  # 自己申告 resolved × LLM unmentioned

    def test_analyze_empty_and_missing_log(self, tmp_path):
        """空ログ・存在しないファイルでも例外にせず件数 0 を返すこと (Q10 契約)。"""
        missing = analyze_shadow_log(tmp_path / "missing.jsonl")
        assert missing["total"] == 0
        assert missing["agreement_rate"] == 0.0

        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        result = analyze_shadow_log(empty)
        assert result["total"] == 0

    def test_analyze_rates(self, tmp_path):
        """一致率・過大申告率が再現可能な数値で返ること。"""
        log_path = tmp_path / "shadow.jsonl"
        rows = [
            ("resolved", "RESOLVED", "resolved"),      # 一致
            ("progressed", "PROGRESSED", "progressed"),  # 一致
            ("unmentioned", "RESOLVED", "resolved"),   # 不一致 + 過大申告
            ("resolved", "PROGRESSED", None),          # 不一致
        ]
        for llm_action, status, meta in rows:
            record_vote_shadow(
                book_id=1, episode_num=1, foreshadowing_id=1, foreshadowing_title="t",
                llm_action=llm_action, judgment_status=status, metadata_action=meta,
                output_path=log_path,
            )
        result = analyze_shadow_log(log_path)
        assert result["total"] == 4
        assert result["agreements"] == 2
        assert result["agreement_rate"] == 0.5
        assert result["metadata_over_reports"] == 1
        # metadata_action 付きは 3 件中 1 件が過大申告 (小数 4 桁に丸められる)
        assert result["metadata_over_report_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert result["llm_action_counts"]["resolved"] == 2

    def test_recording_failure_never_raises(self, tmp_path, monkeypatch):
        """書き込み先が不正でも例外を投げないこと (P3)。"""
        # ディレクトリをファイルとして作り、open を失敗させる
        bad_path = tmp_path / "as_file"
        bad_path.write_text("", encoding="utf-8")
        ok = record_vote_shadow(
            book_id=1, episode_num=1, foreshadowing_id=1, foreshadowing_title="t",
            llm_action="resolved", judgment_status="RESOLVED",
            output_path=bad_path / "nested" / "shadow.jsonl",
        )
        assert ok is False


class TestServiceShadowIntegration:
    def _run_shadow_service(self, monkeypatch, tmp_path, llm_action: str | None):
        """shadow モードで service を実行し、記録と判定を返す。"""
        from src.audit.calibration_store import clear_cache

        monkeypatch.setattr(
            vote_config,
            "get_calibration",
            lambda *a, **kw: {"foreshadowing": {"mode": "shadow"}},
        )
        clear_cache()

        class _StubVoter:
            def __init__(self):
                self.calls = 0

            async def vote(self, **kwargs):
                self.calls += 1

                class _R:
                    action = llm_action
                    evidence_quote = "q"

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

        voter = _StubVoter()
        svc = ForeshadowingService(_FakeRepo(), llm_voter=voter)
        md = WritingMetadata(episode_number=2, foreshadowings=[ForeshadowingReport(foreshadowing_id=1, action="resolved")])
        log_path = tmp_path / "shadow.jsonl"

        import src.engine.foreshadowing.vote_shadow as shadow_mod

        monkeypatch.setattr(shadow_mod, "DEFAULT_SHADOW_PATH", log_path)
        resolved = asyncio.run(
            svc.check_and_resolve(1, 2, "魔剣が抜かれた。", writing_metadata=md, contract_ids=[1])
        )
        return resolved, log_path, voter

    def test_shadow_records_but_verdict_is_legacy(self, monkeypatch, tmp_path):
        """shadow モード: 記録は行われるが、判定は legacy (metadata 40+契約 35=75→RESOLVED) のまま。"""
        resolved, log_path, voter = self._run_shadow_service(monkeypatch, tmp_path, "resolved")
        assert resolved == ["魔剣"]
        assert voter.calls == 1
        data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert data["llm_action"] == "resolved"
        assert data["judgment_status"] == "RESOLVED"  # legacy 判定 (第 4 票を加算しなくても RESOLVED)
        assert data["syntax_score"] == 0

    def test_shadow_disagreement_recorded_for_over_report(self, monkeypatch, tmp_path):
        """自己申告 resolved × LLM unmentioned の過大申告が記録されること (R3 の判断材料)。"""
        resolved, log_path, _ = self._run_shadow_service(monkeypatch, tmp_path, "unmentioned")
        assert resolved == ["魔剣"]  # legacy 判定は変わらない (自己申告バイアスが残る)
        data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert data["metadata_over_report"] is True
        assert data["agree"] is False
