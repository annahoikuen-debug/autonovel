"""v5.3 長編耐性（伏線ステートマシン実体化・プロンプト配線）の回帰テスト。

v5.2 までの実装には、伏線回収が「動くように見えるが実際には動かない」
複数の配線欠落があった。本テストはその欠落が再発しないことを固定化する。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.context_builder_agent import ContextBuilderAgent
from src.agents.specialists.consistency_auditor import (
    _extract_foreshadowing_descriptions,
)
from src.models.foreshadowing_status import ForeshadowingScope, ForeshadowingStatus
from src.services.foreshadowing.planner import (
    DEFAULT_TOTAL_EPISODES,
    plan_foreshadowing,
)


# ── 1. ステートマシンの遷移ガード ───────────────────────────────


class TestForeshadowingStateMachine:
    def test_allowed_transitions(self):
        assert ForeshadowingStatus.can_transition("planted", "progressed")
        assert ForeshadowingStatus.can_transition("planted", "resolved")
        assert ForeshadowingStatus.can_transition("planted", "abandoned")
        assert ForeshadowingStatus.can_transition("progressed", "resolved")
        assert ForeshadowingStatus.can_transition("progressed", "abandoned")

    def test_terminal_states_are_sink(self):
        """終端状態からは遷移できない（回収済み伏線の巻き戻しは事故）"""
        assert not ForeshadowingStatus.can_transition("resolved", "planted")
        assert not ForeshadowingStatus.can_transition("resolved", "progressed")
        assert not ForeshadowingStatus.can_transition("abandoned", "planted")
        assert ForeshadowingStatus.allowed_transitions("resolved") == frozenset()

    def test_self_transition_from_planted_rejected(self):
        """planted → planted は誤った再設置なので拒否"""
        assert not ForeshadowingStatus.can_transition("planted", "planted")

    def test_unknown_status_rejected(self):
        assert not ForeshadowingStatus.can_transition("bogus", "resolved")
        assert not ForeshadowingStatus.can_transition("planted", "bogus")
        assert ForeshadowingStatus.allowed_transitions("bogus") == frozenset()

    def test_active_statuses_unchanged(self):
        assert ForeshadowingStatus.active_statuses() == [
            ForeshadowingStatus.PLANTED,
            ForeshadowingStatus.PROGRESSED,
        ]


# ── 2. 設置工作计划（target_episode が必ず決まる） ─────────────


class TestForeshadowingPlanner:
    def test_target_episode_always_assigned(self):
        """v5.2 の致命的な欠陥: target_episode が常に NULL だった

        NULL のままだと is_contracted が常に True となり、
        アンサンブルスコアの「契約ボーナス」が機能しない。
        """
        for ep in range(1, DEFAULT_TOTAL_EPISODES + 1):
            plan = plan_foreshadowing(ep)
            assert plan.target_episode is not None, f"ep={ep} で未設定"
            assert isinstance(plan.target_episode, int)

    def test_short_term_within_horizon(self):
        """短期伏線は回収スロット内で回収される（長引かせない）"""
        for ep in range(1, DEFAULT_TOTAL_EPISODES + 1):
            plan = plan_foreshadowing(ep)
            if plan.scope is ForeshadowingScope.SHORT_TERM:
                assert plan.horizon >= 1, f"ep={ep}: horizon 0 は不可"

    def test_early_plant_is_short_term(self):
        """第1〜3話の設置は次の短期回収 Duties(4,10)が近いので短期"""
        for ep in (1, 2, 3):
            assert plan_foreshadowing(ep).scope is ForeshadowingScope.SHORT_TERM

    def test_midpoint_plant_is_long_term(self):
        """第19〜25話（中期回収ビート）に置かれた伏線は長期"""
        for ep in (19, 20, 24):
            assert plan_foreshadowing(ep).scope is ForeshadowingScope.LONG_TERM, f"ep={ep}"

    def test_horizon_never_zero(self):
        """設置话と同時回收は不可能（horizon 0 は生成されない）"""
        for ep in range(1, DEFAULT_TOTAL_EPISODES + 1):
            assert plan_foreshadowing(ep).horizon >= 1, f"ep={ep}"

    def test_target_strictly_after_planted(self):
        """ステートマシンの不変条件: 設置話より前の回収は禁止"""
        for ep in range(1, DEFAULT_TOTAL_EPISODES + 1):
            plan = plan_foreshadowing(ep)
            assert plan.target_episode > ep, f"ep={ep} → {plan.target_episode}"

    def test_climax_planted_pays_off_within_climax(self):
        """クライマックス中に撒いた伏線は同じクライマックスで回収される"""
        for ep in (33, 34, 35, 36, 37):
            plan = plan_foreshadowing(ep)
            assert 33 <= plan.target_episode <= 38, f"ep={ep} → {plan.target_episode}"

    def test_payoffs_are_spread_not_piled_on_one_episode(self):
        """全伏線が1話に集中するとプロンプトが過負荷になるため分散させる"""
        from collections import Counter

        counts = Counter(plan_foreshadowing(ep).target_episode for ep in range(1, 41))
        assert max(counts.values()) <= 3, f"回収先の集中: {dict(counts)}"

    def test_climax_aims_at_long_term_payoff_window(self):
        """第19話以降の長期伏線はクライマックス区間(33,38)付近を狙う"""
        for ep in (26, 27, 28, 29, 30, 31, 32):
            plan = plan_foreshadowing(ep)
            assert 33 <= plan.target_episode <= 38, f"ep={ep} → {plan.target_episode}"

    def test_total_episodes_respected(self):
        """回収先は作品の話数を超えない"""
        for total in (10, 20, 40):
            for ep in range(1, total + 1):
                plan = plan_foreshadowing(ep, total_episodes=total)
                assert plan.target_episode <= total or ep >= total

    def test_horizon_never_zero_when_total_equals_planted(self):
        """Step 12: `total == planted`（= promotion_service の最終プロット行）でも horizon 0 を出さない

        旧実装は `min(..., total)` でクランプし、`total == planted` のとき
        39/39 件すべて `target == planted`（回収不能）になっていた。
        """
        for ep in range(1, DEFAULT_TOTAL_EPISODES + 1):
            plan = plan_foreshadowing(ep, total_episodes=ep)
            assert plan.horizon >= 1, f"ep={ep} → target={plan.target_episode}"
            assert plan.target_episode > ep, f"ep={ep} → target={plan.target_episode}"

    def test_none_total_episodes_is_accepted(self):
        """Step 12 (M15): `plan_foreshadowing(1, None)` が TypeError にならない"""
        plan = plan_foreshadowing(1, None)
        assert plan.target_episode > 1
        assert plan.horizon >= 1

    def test_plan_is_immutable(self):
        plan = plan_foreshadowing(3)
        with pytest.raises(Exception):
            plan.target_episode = 99  # type: ignore[misc]


# ── 3. プロンプトへの伏線ID配線 ───────────────────────────────


class TestForeshadowingPromptWiring:
    def test_id_is_rendered(self):
        """ID が無いと LLM が回収を報告できず、伏線が放置される"""
        f = SimpleNamespace(
            id=77, title="聖剣の封印", planted_episode=2,
            description="古代遺跡で発見された封印", target_episode=10, status="planted",
        )
        text = ContextBuilderAgent.format_unresolved_foreshadowings([f])
        assert "- **77**" in text
        assert "聖剣の封印" in text
        assert "第10話回収予定" in text

    def test_consistency_auditor_can_parse_output(self):
        """出力書式が ConsistencyAuditor のパーサと一致すること"""
        f = SimpleNamespace(
            id=99, title="黒騎士の紋章", planted_episode=1,
            description="壁に掛けられた古い紋章", target_episode=20, status="progressed",
        )
        text = ContextBuilderAgent.format_unresolved_foreshadowings([f])
        descriptions = _extract_foreshadowing_descriptions(text)
        assert len(descriptions) == 1
        assert "黒騎士の紋章" in descriptions[0]

    def test_missing_id_is_tolerated(self):
        """id を持たないプロット由来の伏線でも破綻しない"""
        f = SimpleNamespace(
            title="未登録伏線", planted_episode=4, description="d",
            target_episode=None, status="planted",
        )
        text = ContextBuilderAgent.format_unresolved_foreshadowings([f])
        assert "未登録伏線" in text
        assert "- **" not in text

    def test_always_has_section_header(self):
        f = SimpleNamespace(id=1, title="x", planted_episode=1, description="",
                            target_episode=None, status="planted")
        text = ContextBuilderAgent.format_unresolved_foreshadowings([f])
        assert "伏線" in text
    def test_empty_returns_none_marker(self):
        assert ContextBuilderAgent.format_unresolved_foreshadowings([]) == "なし"


# ── 4. Rescheduler が本物の API を呼ぶ ────────────────────────


class TestReschedulerUsesRealApi:
    @pytest.mark.asyncio
    async def test_calls_update_target_episode(self):
        """v5.2: DbForeshadowingRepository に update_target_episode が無く
        hasattr ガードでサイレント no-op + 偽成功ログになっていた"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        repo = MagicMock()
        repo.update_target_episode = AsyncMock(return_value=True)
        result = await ForeshadowingRescheduler.reschedule_foreshadowing(
            foreshadowing_id=5, current_episode=3, repo=repo,
        )
        assert result is not None
        repo.update_target_episode.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_api_returns_none_not_fake_success(self):
        """API が無い場合は成功を偽装せず None を返す"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        repo = SimpleNamespace()  # update_target_episode を持たない
        result = await ForeshadowingRescheduler.reschedule_foreshadowing(
            foreshadowing_id=5, current_episode=3, repo=repo,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_rejected_update_returns_none(self):
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        repo = MagicMock()
        repo.update_target_episode = AsyncMock(return_value=False)
        result = await ForeshadowingRescheduler.reschedule_foreshadowing(
            foreshadowing_id=5, current_episode=3, repo=repo,
        )
        assert result is None

    def test_find_next_suitable_is_after_current(self):
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        for cur in (1, 5, 10, 20, 30, 39):
            nxt = ForeshadowingRescheduler.find_next_suitable_episode(cur, 40)
            assert nxt is None or nxt > cur, f"cur={cur} → {nxt}"

    def test_long_book_postponement_is_not_killed_by_40(self):
        """Step 15 (M2): `max_episode=40` 固定を廃止し、100话本でも延期が機能する"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        for cur in (45, 60, 80, 100, 120):
            nxt = ForeshadowingRescheduler.find_next_suitable_episode(cur)
            assert nxt is not None, f"cur={cur}: 上限なしで延期不能にしている"
            assert nxt > cur, f"cur={cur} → {nxt}"

    def test_postponement_beyond_fixed_40_default(self):
        """旧既定値 40 のままでは 45话以降の延期先が 40话以下へ巻き戻っていた"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        nxt = ForeshadowingRescheduler.find_next_suitable_episode(60, max_episode=120)
        assert nxt > 60, f"61..120 の範囲へ延期されるべき: {nxt}"

    def test_no_upper_bound_never_rewinds_to_earlier_episode(self):
        """Step 16: 回収ビートが無い即使に `min(cur+2, max)` で現在话以下を返さない"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        # 総话数を超過している = 延期不能（None）か、せめて現在话より後
        for cur in (100, 200):
            nxt = ForeshadowingRescheduler.find_next_suitable_episode(cur, max_episode=cur)
            assert nxt is None, f"cur={cur}: 延期不能なら None を返す（{nxt} は偽の延期）"

    def test_postponement_impossible_returns_none(self):
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        assert ForeshadowingRescheduler.find_next_suitable_episode(40, max_episode=40) is None

    @pytest.mark.asyncio
    async def test_postponement_impossible_does_not_fake_success(self):
        """Step 16: 延期不能時は update_target_episode を呼ばない"""
        from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

        repo = MagicMock()
        repo.update_target_episode = AsyncMock(return_value=True)
        result = await ForeshadowingRescheduler.reschedule_foreshadowing(
            foreshadowing_id=5, current_episode=40, repo=repo, max_episode=40,
        )
        assert result is None
        repo.update_target_episode.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_max_episode_is_propagated_from_service(self, monkeypatch):
        """Step 15: `check_and_resolve` の total_episodes が延期の上限として伝わる"""
        import src.services.foreshadowing_service as svc_mod
        from src.services.foreshadowing_service import ForeshadowingService

        captured = {}

        async def _fake_reschedule(*, foreshadowing_id, current_episode, repo, max_episode=None):
            captured["max_episode"] = max_episode
            return current_episode + 2

        monkeypatch.setattr(
            svc_mod.ForeshadowingRescheduler, "reschedule_foreshadowing", _fake_reschedule
        )

        f = SimpleNamespace(
            id=1, title="伏線A", description="d", planted_episode=1,
            target_episode=5, status="planted", keywords=[],
        )
        repo = MagicMock()
        repo.get_unresolved = AsyncMock(return_value=[f])
        repo.progress = AsyncMock(return_value=True)
        repo.update_target_episode = AsyncMock(return_value=True)

        service = ForeshadowingService(repo)
        await service.check_and_resolve(
            book_id=1, episode_num=5, draft_text="伏線Aが動いた",
            contract_ids=[1], total_episodes=120,
        )
        assert captured["max_episode"] == 120

    @pytest.mark.asyncio
    async def test_progressed_to_progressed_is_normal_not_warning(self, caplog):
        """Step 14 (M1): progress() の拒否は異常ではなく「変化なし」として扱う"""
        from src.services.foreshadowing_service import ForeshadowingService

        f = SimpleNamespace(
            id=1, title="伏線B", description="d", planted_episode=1,
            target_episode=5, status="progressed", keywords=[],
        )
        repo = MagicMock()
        repo.get_unresolved = AsyncMock(return_value=[f])
        # progressed → progressed はガードで拒否される（False）
        repo.progress = AsyncMock(return_value=False)
        repo.update_target_episode = AsyncMock(return_value=True)

        service = ForeshadowingService(repo)
        with caplog.at_level("INFO", logger="src.services.foreshadowing_service"):
            resolved = await service.check_and_resolve(
                book_id=1, episode_num=5, draft_text="伏線Bがさらに動いた",
                contract_ids=[1],
            )
        assert resolved == []
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "既に PROGRESSED（変化なし）" in messages
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    @pytest.mark.asyncio
    async def test_progressed_success_logs_update(self, caplog):
        """Step 14: 遷移が成功したときだけ成功ログを出す"""
        from src.services.foreshadowing_service import ForeshadowingService

        f = SimpleNamespace(
            id=2, title="伏線C", description="d", planted_episode=1,
            target_episode=5, status="planted", keywords=[],
        )
        repo = MagicMock()
        repo.get_unresolved = AsyncMock(return_value=[f])
        repo.progress = AsyncMock(return_value=True)
        repo.update_target_episode = AsyncMock(return_value=True)

        service = ForeshadowingService(repo)
        with caplog.at_level("INFO", logger="src.services.foreshadowing_service"):
            await service.check_and_resolve(
                book_id=1, episode_num=5, draft_text="伏線Cが動いた", contract_ids=[2],
            )
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "PROGRESSED に更新" in messages
        assert "変化なし" not in messages

    @pytest.mark.asyncio
    async def test_empty_contract_ids_is_distinct_from_none(self):
        """Step 17 (M14): 契約0件([]) と契約情報なし(None) を区別する"""
        from src.services.foreshadowing_service import ForeshadowingService

        f = SimpleNamespace(
            id=3, title="伏線D", description="d", planted_episode=1,
            target_episode=None, status="planted", keywords=[],
        )
        repo = MagicMock()
        repo.get_unresolved = AsyncMock(return_value=[f])
        repo.resolve = AsyncMock(return_value=True)
        repo.progress = AsyncMock(return_value=True)
        repo.update_target_episode = AsyncMock(return_value=True)

        service = ForeshadowingService(repo)
        resolved = await service.check_and_resolve(
            book_id=1, episode_num=2, draft_text="伏線Dの正体が 밝혀られた",
            contract_ids=[],
        )
        # 契約0件・target 無し = 契約済みではない（35pt の契約ボーナスなし）
        assert resolved == []
        repo.resolve.assert_not_awaited()


# ── 5. 伏線KPI（回収率の定量化） ───────────────────────────────


class TestForeshadowingKpi:
    def _service(self, balance, overdue=()):
        from src.services.foreshadowing.kpi import ForeshadowingKpiService

        repo = MagicMock()
        repo.get_balance = AsyncMock(return_value=balance)
        repo.get_overdue = AsyncMock(return_value=list(overdue))
        return ForeshadowingKpiService(repo)

    @pytest.mark.asyncio
    async def test_collection_rate(self):
        kpi = await self._service(
            {"planted": 3, "progressed": 2, "resolved": 4, "abandoned": 1}
        ).compute(book_id=1)
        # 終端5本中 4本回収 → 0.8
        assert kpi.collection_rate == 0.8
        assert kpi.active == 5
        assert kpi.resolved == 4
        assert kpi.abandoned == 1

    @pytest.mark.asyncio
    async def test_zero_denominator_is_safe(self):
        kpi = await self._service({}).compute(book_id=1)
        assert kpi.collection_rate == 0.0
        assert kpi.resolution_rate == 0.0

    @pytest.mark.asyncio
    async def test_overdue_counted(self):
        kpi = await self._service(
            {"planted": 2, "progressed": 1, "resolved": 1, "abandoned": 0},
            overdue=[MagicMock(), MagicMock()],
        ).compute(book_id=1, current_episode=20)
        assert kpi.overdue == 2

    @pytest.mark.asyncio
    async def test_metrics_published(self):
        """Prometheus メトリクスが実際に更新される"""
        kpi = await self._service(
            {"planted": 0, "progressed": 0, "resolved": 3, "abandoned": 0}
        ).compute(book_id=42, current_episode=10)
        from src.backend.observability import metrics as m

        value = m.foreshadowing_collection_rate.labels(book_id="42")._value.get()
        assert value == kpi.collection_rate


# ── 6. 3層記憶の実配線 ───────────────────────────────────────


class TestThreeLayerPromptWiring:
    def test_layers_formatted_into_prompt_text(self):
        """v5.2: three_layer_context は組み立てられるだけだった"""
        from src.agents.prompt_composer import PromptComposer

        text = PromptComposer._format_three_layer_context(
            {
                "layer1_bible": {"text": "【ア Propagation】世界設定"},
                "layer2_summary": {"text": "【過去】第1話: CCGakusei発"},
                "layer3_previous": {"text": "直前の本文…"},
            }
        )
        assert "Layer1" in text
        assert "Layer2" in text
        assert "Layer3" in text
        assert "世界設定" in text
        assert "直前の本文" in text

    def test_empty_inputs(self):
        from src.agents.prompt_composer import PromptComposer

        assert PromptComposer._format_three_layer_context(None) == ""
        assert PromptComposer._format_three_layer_context({}) == ""

    def test_raw_layer3_key_supported(self):
        """後方互換: layer3_raw キーでも取り出せる"""
        from src.agents.prompt_composer import PromptComposer

        text = PromptComposer._format_three_layer_context({"layer3_raw": "直前の本文"})
        assert "直前の本文" in text


# ── 7. 契約伏線がプロンプトと判定の両方に渡る ──────────────────


class TestContractForeshadowingWiring:
    @pytest.mark.asyncio
    async def test_loads_from_db_not_plot_json(self, monkeypatch):
        """未回収伏線の正典は foreshadowings テーブル"""
        agent = ContextBuilderAgent.__new__(ContextBuilderAgent)
        agent.logger = MagicMock()

        db_record = SimpleNamespace(
            id=1, title="DB伏線", description="d", planted_episode=1,
            target_episode=5, status="planted",
        )
        repo = MagicMock()
        repo.get_unresolved = AsyncMock(return_value=[db_record])
        service = MagicMock()
        service.get_contract_foreshadowings = AsyncMock(
            return_value=[{"id": 1, "title": "DB伏線"}]
        )
        repo_cls = MagicMock(return_value=repo)
        service_cls = MagicMock(return_value=service)

        import src.infrastructure.repositories.foreshadowing_repo as repo_mod
        import src.services.foreshadowing_service as svc_mod

        monkeypatch.setattr(repo_mod, "DbForeshadowingRepository", repo_cls)
        monkeypatch.setattr(svc_mod, "ForeshadowingService", service_cls)

        unresolved, contract = await ContextBuilderAgent._load_db_foreshadowings(
            agent, MagicMock(), book_id=7, ep_num=5
        )
        assert len(unresolved) == 1
        assert unresolved[0].title == "DB伏線"
        assert contract[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_no_session_returns_empty(self):
        agent = ContextBuilderAgent.__new__(ContextBuilderAgent)
        agent.logger = MagicMock()
        unresolved, contract = await ContextBuilderAgent._load_db_foreshadowings(
            agent, None, book_id=7, ep_num=5
        )
        assert unresolved == []
        assert contract == []


# ── 8. 長編ベンチマークが健全な値を返す ───────────────────────


class TestLongFormBenchmark:
    @pytest.mark.parametrize("total", [20, 50, 100])
    def test_completion_rate_is_full(self, total):
        from tests.benchmarks.long_form import run_long_form

        report = run_long_form(total)
        assert report.completion_rate == 1.0

    def test_layer2_stays_bounded_as_series_grows(self):
        """層2が話数に比例して膨らまないこと（長編破綻の主要因）

        v5.2 は過去話全文を無制限に積み上げていたため、N話目で
        コンテキストが N に比例して肥大していた。v5.3 のバジェット制御で
        50話以降の文字数がプラトーになることを確認する。
        """
        from tests.benchmarks.long_form import run_long_form

        at_100 = run_long_form(100).layer2_chars_max
        at_200 = run_long_form(200).layer2_chars_max

        # 50話で既にプラトーに達している
        assert at_100 <= run_long_form(50).layer2_chars_max * 1.05
        # 100話→200話でほぼ増えない（線形成長しない）
        assert at_200 <= at_100 * 1.05, f"Layer2 が線形成長: {at_100} → {at_200}"
        # 絶対的な上限も守る
        assert at_200 <= 4000, f"Layer2 が予算超過: {at_200}"

    def test_layer2_plateaus_not_linear(self):
        """10倍の話数で Layer2 が10倍以上膨らまない"""
        from tests.benchmarks.long_form import run_long_form

        small = run_long_form(10).layer2_chars_max
        large = run_long_form(100).layer2_chars_max
        assert large < small * 3, f"Layer2 が話数に比例: {small} → {large}"

    def test_collection_rate_is_high(self):
        from tests.benchmarks.long_form import run_long_form

        report = run_long_form(40)
        assert report.collection_rate >= 0.9, f"回収率が低い: {report.collection_rate}"

    def test_no_foreshadowing_resolved_before_planted(self):
        """設置話より前の回収はステートachine invariants により禁止"""
        from tests.benchmarks.long_form import run_long_form

        report = run_long_form(50)
        # 不変条件違反があれば resolved 数が inflated になる
        assert report.resolved <= report.planted
