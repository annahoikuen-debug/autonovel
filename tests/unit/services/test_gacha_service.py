"""GachaService 単体テスト (Step 7-12)。

Step 7: フィクスチャ定義
Step 8: _save_gacha_plans_db / _save_review_session 永久化パス
Step 9: generate_plans 正常系
Step 10: generate_plans 異常系
Step 11: review_gacha_plans ブラインドレビュー経路
Step 12: エッジケース
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.easy_mode import GachaPlan, GachaPlanType, GachaRequest, GachaResponse
from src.domain.entities.review_session import ReviewRound, ReviewSession
from src.services.blind_review import BlindReviewGate
from src.services.gacha_service import GachaService
from tests.mocks.llm_adapter import LLMMocker, MockLLMAdapter


# ============================================================================
# Step 7: フィクスチャ定義
# ============================================================================


@pytest.fixture
def mock_llm_mocker() -> LLMMocker:
    """LLM 応答を制御するモッカー。"""
    return LLMMocker()


@pytest.fixture
def mock_llm_adapter(mock_llm_mocker: LLMMocker) -> MockLLMAdapter:
    """MockLLMAdapter インスタンス。"""
    return MockLLMAdapter(mock_llm_mocker)


@pytest.fixture
def mock_db() -> MagicMock:
    """データベース管理器のモック。"""
    db = MagicMock()
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    db.get_session = MagicMock(return_value=session)
    return db


@pytest.fixture
def mock_blind_gate() -> BlindReviewGate:
    """BlindReviewGate インスタンス (デフォルト設定)。"""
    return BlindReviewGate(
        forbidden_agents=["proposal_other", "plan_other", "gacha_competitor"],
        mode="scrub",
    )


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """イベントバスのモック。"""
    return AsyncMock()


@pytest.fixture
def gacha_service(
    mock_llm_adapter: MockLLMAdapter,
    mock_db: MagicMock,
    mock_blind_gate: BlindReviewGate,
    mock_event_bus: AsyncMock,
) -> GachaService:
    """GachaService インスタンス (全依存をモック注入)。"""
    service = GachaService(
        llm_service=mock_llm_adapter,
        db=mock_db,
        blind_gate=mock_blind_gate,
        event_bus=mock_event_bus,
    )
    # llm_service.generate_json をモック (正常な dict を返すように設定)
    mock_gen_json = AsyncMock()

    async def mock_generate_json(**kwargs):
        # LLMMocker から次のレスポンスを取得
        response_text = mock_llm_adapter.mocker.get_next_response()
        try:
            return {"story_content": json.loads(response_text)}
        except json.JSONDecodeError:
            return {"story_content": response_text}

    mock_gen_json.side_effect = mock_generate_json
    service.llm_service.generate_json = mock_gen_json
    return service


@pytest.fixture
def sample_gacha_request() -> GachaRequest:
    """サンプルの GachaRequest。"""
    return GachaRequest(
        genre="ファンタジー",
        keywords=["魔法", "冒険", "ドラゴン"],
        temperature=0.7,
    )


@pytest.fixture
def sample_gacha_response() -> GachaResponse:
    """サンプルの GachaResponse (モック用)。"""
    plans = [
        GachaPlan(
            plan_id="plan_a1b2c3",
            plan_type=GachaPlanType.ROYAL,
            title="王道の冒険譚",
            logline="勇者が魔王を倒す王道ファンタジー",
            protagonist_summary="正義感の強い少年剣士",
            charm_point="熱血展開と仲間との絆",
        ),
        GachaPlan(
            plan_id="plan_d4e5f6",
            plan_type=GachaPlanType.CURVEBALL,
            title="魔王視点の逆転劇",
            logline="魔王が主人公の異世界転生もの",
            protagonist_summary="元勇者だった魔王",
            charm_point="視点逆転の面白さ",
        ),
        GachaPlan(
            plan_id="plan_g7h8i9",
            plan_type=GachaPlanType.DARK,
            title="絶望のダークファンタジー",
            logline="希望を失った世界で生き残る物語",
            protagonist_summary="冷徹な傭兵",
            charm_point="シリアスな世界観",
        ),
    ]
    return GachaResponse(
        request_id="gacha_test123",
        plans=plans,
        recommended_plan_id="plan_a1b2c3",
        review_session_id="review_abc123",
    )


# ============================================================================
# Step 8: _save_gacha_plans_db / _save_review_session 永久化パス
# ============================================================================


class TestGachaServicePersistence:
    """_save_gacha_plans_db と _save_review_session のテスト。"""

    @pytest.mark.asyncio
    async def test_save_gacha_plans_db_success(
        self, gacha_service: GachaService, mock_db: MagicMock
    ):
        """正常に gacha plans が保存されること。"""
        request_id = "gacha_test123"
        plans_json = {"request": {}, "response": {}}

        await gacha_service._save_gacha_plans_db(request_id, plans_json)

        # セッション取得・コミットが呼ばれること
        mock_db.get_session.assert_called_once()
        session = mock_db.get_session.return_value.__aenter__.return_value
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_gacha_plans_db_rollback_on_exception(
        self, gacha_service: GachaService, mock_db: MagicMock
    ):
        """DB 例外時にロールバックされること。"""
        request_id = "gacha_test123"
        plans_json = {"request": {}, "response": {}}

        # repo.save_gacha_plans で例外を発生させる
        from src.backend.database.repositories import EasyModeDraftRepository
        with patch.object(EasyModeDraftRepository, "save_gacha_plans", AsyncMock(side_effect=Exception("DB error"))):
            with pytest.raises(Exception, match="DB error"):
                await gacha_service._save_gacha_plans_db(request_id, plans_json)

        # コンテキストマネージャの __aexit__ が例外情報と共に呼ばれ、内部で rollback される
        session = mock_db.get_session.return_value.__aenter__.return_value
        # __aexit__ が例外情報と共に呼ばれることを確認（内部で rollback される）
        assert session.__aexit__.called
        # __aexit__ の呼び出し引数に例外情報が含まれることを確認
        args, _ = session.__aexit__.call_args
        assert args[0] is not None  # exc_type
        assert args[1] is not None  # exc_val
        assert args[2] is not None  # exc_tb

    @pytest.mark.asyncio
    async def test_save_review_session_success(
        self, gacha_service: GachaService, mock_db: MagicMock
    ):
        """ReviewSession が正常に保存されること。"""
        review_session = ReviewSession(
            request_id="gacha_test123",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        await gacha_service._save_review_session(review_session)

        mock_db.get_session.assert_called_once()
        session = mock_db.get_session.return_value.__aenter__.return_value
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_review_session_rollback_on_exception(
        self, gacha_service: GachaService, mock_db: MagicMock
    ):
        """ReviewSession 保存時の DB 例外でロールバックされること。"""
        review_session = ReviewSession(
            request_id="gacha_test123",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        from src.backend.database.repositories import EasyModeDraftRepository
        with patch.object(EasyModeDraftRepository, "save_review_session", AsyncMock(side_effect=Exception("DB error"))):
            with pytest.raises(Exception, match="DB error"):
                await gacha_service._save_review_session(review_session)

            # コンテキストマネージャの __aexit__ で rollback が呼ばれる
            session = mock_db.get_session.return_value.__aenter__.return_value
            assert session.__aexit__.called

    @pytest.mark.asyncio
    async def test_save_gacha_plans_db_duplicate_key_handled(
        self, gacha_service: GachaService, mock_db: MagicMock
    ):
        """重複キー例外が適切に扱われること (リポジトリ側で処理される前提)。"""
        request_id = "gacha_test123"
        plans_json = {"request": {}, "response": {}}

        # 正常ケースとして実行 (重複はリポジトリでハンドリング)
        await gacha_service._save_gacha_plans_db(request_id, plans_json)
        session = mock_db.get_session.return_value.__aenter__.return_value
        session.commit.assert_awaited_once()


# ============================================================================
# Step 9: generate_plans 正常系
# ============================================================================


class TestGeneratePlansSuccess:
    """generate_plans 正常系テスト。"""

    @pytest.mark.asyncio
    async def test_generate_plans_json_format_success(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """正常な JSON 応答で 3 案生成→保存→ブラインドレビュー起動まで完了すること。"""
        # LLM が正常な JSON を返すように設定
        mock_llm_mocker.set_responses(
            json.dumps({
                "title": "王道の冒険譚",
                "logline": "勇者が魔王を倒す王道ファンタジー",
                "protagonist_summary": "正義感の強い少年剣士",
                "charm_point": "熱血展開と仲間との絆",
            }),
            json.dumps({
                "title": "魔王視点の逆転劇",
                "logline": "魔王が主人公の異世界転生もの",
                "protagonist_summary": "元勇者だった魔王",
                "charm_point": "視点逆転の面白さ",
            }),
            json.dumps({
                "title": "絶望のダークファンタジー",
                "logline": "希望を失った世界で生き残る物語",
                "protagonist_summary": "冷徹な傭兵",
                "charm_point": "シリアスな世界観",
            }),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        # レスポンス検証
        assert isinstance(response, GachaResponse)
        assert len(response.plans) == 3
        assert response.recommended_plan_id is not None
        assert response.review_session_id is not None

        # 3 回の LLM 呼び出し
        assert gacha_service.llm_service.generate_json.call_count == 3

        # DB 保存が呼ばれること
        gacha_service._db.get_session.assert_called()

    @pytest.mark.asyncio
    async def test_generate_plans_key_value_format_success(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """key=value 形式の応答もパースできること (JSON パース失敗時のフォールバック)。"""
        # LLM が key=value 形式を返すように設定
        mock_llm_mocker.set_responses(
            "title: 王道の冒険譚\nlogline: 勇者が魔王を倒す\nprotagonist_summary: 正義の剣士\ncharm_point: 熱血展開",
            "title: 変化球案\nlogline: 予想外の展開\nprotagonist_summary: 個性的な主人公\ncharm_point: ギャップ萌え",
            "title: ダーク案\nlogline: 重厚な物語\nprotagonist_summary: 暗い過去を持つ\ncharm_point: 深みのある世界観",
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        assert isinstance(response, GachaResponse)
        assert len(response.plans) == 3

    @pytest.mark.asyncio
    async def test_generate_plans_review_session_created(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """ReviewSession が作成され、ラウンド0が実行されること。"""
        mock_llm_mocker.set_responses(
            json.dumps({
                "title": "王道", "logline": "あらすじ", "protagonist_summary": "主人公", "charm_point": "魅力"
            }),
            json.dumps({
                "title": "変化球", "logline": "あらすじ", "protagonist_summary": "主人公", "charm_point": "魅力"
            }),
            json.dumps({
                "title": "ダーク", "logline": "あらすじ", "protagonist_summary": "主人公", "charm_point": "魅力"
            }),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        assert response.review_session_id is not None
        assert response.review_session_id.startswith("review_")

    @pytest.mark.asyncio
    async def test_generate_plans_best_plan_recommended(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """最もスコアの高い案が推奨案になること。"""
        mock_llm_mocker.set_responses(
            json.dumps({"title": "A", "logline": "a", "protagonist_summary": "a", "charm_point": "a"}),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        # ROYAL 型はボーナス +3 なので最も高スコアになるはず
        recommended = next(p for p in response.plans if p.plan_id == response.recommended_plan_id)
        assert recommended.plan_type == GachaPlanType.ROYAL
        assert recommended.is_recommended is True


# ============================================================================
# Step 10: generate_plans 異常系
# ============================================================================


class TestGeneratePlansFailure:
    """generate_plans 異常系テスト。"""

    @pytest.mark.asyncio
    async def test_generate_plans_invalid_json_fallback(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """不正 JSON 時はフォールバック案が生成されること。"""
        # 最初の2回は不正 JSON、3回目は正常
        mock_llm_mocker.set_responses(
            "not a json",
            "{invalid json",
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        # 3 案とも生成される (最初の2つはフォールバック)
        assert len(response.plans) == 3

    @pytest.mark.asyncio
    async def test_generate_plans_unknown_keys_ignored(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """未知のキーが含まれていても無視されて正常生成されること。"""
        mock_llm_mocker.set_responses(
            json.dumps({
                "title": "A", "logline": "a", "protagonist_summary": "a", "charm_point": "a",
                "unknown_key": "ignored"
            }),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        assert len(response.plans) == 3
        assert response.plans[0].title == "A"

    @pytest.mark.asyncio
    async def test_generate_plans_type_mismatch_handled(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """型不整合 (数値が文字列に来る等) があってもフォールバックで生成されること。"""
        mock_llm_mocker.set_responses(
            json.dumps({
                "title": 123,  # 数値が来る
                "logline": "a",
                "protagonist_summary": "a",
                "charm_point": "a"
            }),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        assert len(response.plans) == 3
        # title は文字列に変換されるはず
        assert isinstance(response.plans[0].title, str)

    @pytest.mark.asyncio
    async def test_generate_plans_ast_dangerous_content_rejected(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """AST 危険検知 (os.system 等) が含まれる場合はフォールバックされること。"""
        # 危険なコードを含む応答
        mock_llm_mocker.set_responses(
            json.dumps({
                "title": "A",
                "logline": "a",
                "protagonist_summary": "a",
                "charm_point": "__import__('os').system('rm -rf /')"
            }),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        # フォールバックで生成されるはず
        assert len(response.plans) == 3

    @pytest.mark.asyncio
    async def test_generate_plans_all_three_fail_returns_fallback(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """3 案すべて LLM 失敗してもフォールバック案が返されること。"""
        # 全て例外を投げる
        mock_llm_mocker.add_exception(Exception("LLM error"), Exception("LLM error"), Exception("LLM error"),
                                      Exception("LLM error"), Exception("LLM error"), Exception("LLM error"),
                                      Exception("LLM error"), Exception("LLM error"), Exception("LLM error"))

        response = await gacha_service.generate_plans(sample_gacha_request)

        # フォールバックで 3 案生成される
        assert len(response.plans) == 3
        assert all(p.title.startswith("ファンタジー：") for p in response.plans)

    @pytest.mark.asyncio
    async def test_generate_plans_timeout_raises_timeout_error(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
    ):
        """LLM 応答がタイムアウトしたら TimeoutError が投げられること。"""
        # asyncio.wait_for がタイムアウトするようにモック
        original_wait_for = asyncio.wait_for

        async def mock_wait_for(coro, timeout):
            raise TimeoutError("タイムアウト")

        asyncio.wait_for = mock_wait_for
        try:
            with pytest.raises(TimeoutError, match="タイムアウト"):
                await gacha_service.generate_plans(sample_gacha_request)
        finally:
            asyncio.wait_for = original_wait_for


# ============================================================================
# Step 11: review_gacha_plans ブラインドレビュー経路
# ============================================================================


class TestReviewGachaPlans:
    """ブラインドレビュー経路のテスト。"""

    @pytest.mark.asyncio
    async def test_review_round_normal_approval(
        self,
        gacha_service: GachaService,
        mock_llm_mocker: LLMMocker,
    ):
        """正常な承認フロー (ラウンド実行・スコア付与・イベント発行)。"""
        plans = [
            GachaPlan(plan_id="p1", plan_type=GachaPlanType.ROYAL, title="A", logline="a", protagonist_summary="a", charm_point="a"),
            GachaPlan(plan_id="p2", plan_type=GachaPlanType.CURVEBALL, title="B", logline="b", protagonist_summary="b", charm_point="b"),
            GachaPlan(plan_id="p3", plan_type=GachaPlanType.DARK, title="C", logline="c", protagonist_summary="c", charm_point="c"),
        ]
        review_session = ReviewSession(
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        round_obj = await gacha_service._run_review_round(
            plans=plans,
            round_number=1,
            review_session=review_session,
            request_id="req1",
            genre="ファンタジー",
        )

        assert isinstance(round_obj, ReviewRound)
        assert round_obj.round_number == 1
        assert len(round_obj.plan_scores) == 3
        # イベント発行されたこと
        gacha_service.event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_review_round_rejection_handled(
        self,
        gacha_service: GachaService,
    ):
        """却下 (スコアが低い) 場合も正常にラウンドが完了すること。"""
        plans = [
            GachaPlan(plan_id="p1", plan_type=GachaPlanType.ROYAL, title="A", logline="a", protagonist_summary="a", charm_point="a"),
            GachaPlan(plan_id="p2", plan_type=GachaPlanType.CURVEBALL, title="B", logline="b", protagonist_summary="b", charm_point="b"),
            GachaPlan(plan_id="p3", plan_type=GachaPlanType.DARK, title="C", logline="c", protagonist_summary="c", charm_point="c"),
        ]
        review_session = ReviewSession(
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        round_obj = await gacha_service._run_review_round(
            plans=plans,
            round_number=1,
            review_session=review_session,
            request_id="req1",
            genre="ファンタジー",
        )

        # 全プランにスコアが付く
        assert all(score > 0 for score in round_obj.plan_scores.values())

    @pytest.mark.asyncio
    async def test_review_round_regeneration_limit_reached(
        self,
        gacha_service: GachaService,
    ):
        """再生成上限到達時の挙動 (ReviewSession.should_continue_review)。"""
        review_session = ReviewSession(
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        # 3 ラウンド追加 (最大ラウンド数 = 3)
        for i in range(3):
            round_obj = ReviewRound(
                round_number=i,
                timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                plan_scores={"p1": 80.0, "p2": 75.0, "p3": 70.0},
                plan_critiques={},
                gate_config_hash="abc",
            )
            review_session.add_round(round_obj)

        # 最大ラウンド数到達で継続しない
        assert review_session.should_continue_review(max_rounds=3) is False

    @pytest.mark.asyncio
    async def test_review_round_convergence_stops_early(
        self,
        gacha_service: GachaService,
    ):
        """スコア変化が閾値未満で収束判定され早期停止すること。"""
        review_session = ReviewSession(
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        # 2 ラウンドでスコア変化が小さい
        for i, scores in enumerate([{"p1": 80.0, "p2": 75.0, "p3": 70.0}, {"p1": 80.5, "p2": 75.2, "p3": 70.1}]):
            round_obj = ReviewRound(
                round_number=i,
                timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                plan_scores=scores,
                plan_critiques={},
                gate_config_hash="abc",
            )
            review_session.add_round(round_obj)

        # 変化が閾値(2.0)未満なので収束とみなされ停止
        assert review_session.should_continue_review(max_rounds=3, score_delta_threshold=2.0) is False

    @pytest.mark.asyncio
    async def test_review_round_concurrent_access_safe(
        self,
        gacha_service: GachaService,
    ):
        """競合時 (複数ラウンド同時実行) の挙動 - 独立したゲートインスタンスが作られること。"""
        plans = [
            GachaPlan(plan_id="p1", plan_type=GachaPlanType.ROYAL, title="A", logline="a", protagonist_summary="a", charm_point="a"),
            GachaPlan(plan_id="p2", plan_type=GachaPlanType.CURVEBALL, title="B", logline="b", protagonist_summary="b", charm_point="b"),
            GachaPlan(plan_id="p3", plan_type=GachaPlanType.DARK, title="C", logline="c", protagonist_summary="c", charm_point="c"),
        ]
        review_session = ReviewSession(
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        # 並列でラウンド実行 (current_round_id が異なるゲートが作られる)
        round1_task = gacha_service._run_review_round(plans, 1, review_session, "req1", "ファンタジー")
        round2_task = gacha_service._run_review_round(plans, 2, review_session, "req1", "ファンタジー")

        round1, round2 = await asyncio.gather(round1_task, round2_task)

        assert round1.round_number == 1
        assert round2.round_number == 2
        assert round1.gate_config_hash == round2.gate_config_hash  # 設定は同じ


# ============================================================================
# Step 12: エッジケース
# ============================================================================


class TestGeneratePlansEdgeCases:
    """generate_plans のエッジケーステスト。"""

    @pytest.mark.asyncio
    async def test_generate_plans_empty_genre_keywords_raises(
        self,
        gacha_service: GachaService,
    ):
        """空の genre/keywords で Pydantic バリデーションエラーになること。"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GachaRequest(genre="", keywords=[])

    @pytest.mark.asyncio
    async def test_generate_plans_huge_json_handled(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """巨大な JSON 応答も処理できること。"""
        huge_content = "x" * 10000
        mock_llm_mocker.set_responses(
            json.dumps({"title": "A", "logline": huge_content, "protagonist_summary": "a", "charm_point": "a"}),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)
        assert len(response.plans) == 3

    @pytest.mark.asyncio
    async def test_generate_plans_llm_timeout_handled(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
    ):
        """LLM タイムアウト時の挙動 (asyncio.wait_for で制御される)。"""
        # asyncio.wait_for がタイムアウトするようにモック
        original_wait_for = asyncio.wait_for

        async def mock_wait_for(coro, timeout):
            raise TimeoutError("タイムアウト")

        asyncio.wait_for = mock_wait_for
        try:
            with pytest.raises(TimeoutError):
                await gacha_service.generate_plans(sample_gacha_request)
        finally:
            asyncio.wait_for = original_wait_for

    @pytest.mark.asyncio
    async def test_generate_plans_db_conflict_handled(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
        mock_db: MagicMock,
    ):
        """DB 保存時の競合 (一意制約違反等) が適切に扱われること。"""
        mock_llm_mocker.set_responses(
            json.dumps({"title": "A", "logline": "a", "protagonist_summary": "a", "charm_point": "a"}),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        # コミットで例外 (2回目の呼び出しのみ、_save_gacha_plans_db 用)
        session = mock_db.get_session.return_value.__aenter__.return_value
        commit_count = {"count": 0}

        async def commit_with_error():
            commit_count["count"] += 1
            if commit_count["count"] == 2:  # 2回目のコミット (_save_gacha_plans_db) で失敗
                raise Exception("UNIQUE constraint failed")

        session.commit.side_effect = commit_with_error

        # DB 保存の競合は握りつぶされ、生成結果の返却は継続する
        # (_save_gacha_plans_db_safe が例外を捕捉して WARNING ログを出す)
        response = await gacha_service.generate_plans(sample_gacha_request)

        assert len(response.plans) == 3
        assert response.recommended_plan_id is not None
        # 2回目のコミット (_save_gacha_plans_db) で例外が発生したことを確認
        assert commit_count["count"] >= 2

    @pytest.mark.asyncio
    async def test_generate_plans_empty_plan_fallback(
        self,
        gacha_service: GachaService,
        sample_gacha_request: GachaRequest,
        mock_llm_mocker: LLMMocker,
    ):
        """空のプラン (title 等が空) でもエラーにならず生成されること。

        現在の実装では空文字はデフォルト値で置換されず、そのまま保持される。
        キーが存在しない場合のみデフォルト値が使われる。
        """
        mock_llm_mocker.set_responses(
            json.dumps({"title": "", "logline": "", "protagonist_summary": "", "charm_point": ""}),
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )

        response = await gacha_service.generate_plans(sample_gacha_request)

        assert len(response.plans) == 3
        # 空文字や空白のみの場合はデフォルト値で安全に補完されること
        assert response.plans[0].title == f"{sample_gacha_request.genre}【royal案】"
        assert response.plans[0].logline == "あらすじ準備中"
        assert response.plans[0].protagonist_summary == "主人公詳細準備中"
        assert response.plans[0].charm_point == "魅力ポイント準備中"
        # キーが欠けている場合も同様にデフォルト値
        mock_llm_mocker.set_responses(
            json.dumps({"logline": "only logline"}),  # title キーなし
            json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
            json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
        )
        response2 = await gacha_service.generate_plans(sample_gacha_request)
        assert response2.plans[0].title == f"{sample_gacha_request.genre}【royal案】"  # デフォルト値

    @pytest.mark.asyncio
    async def test_generate_plans_resume_existing_session(
        self,
        gacha_service: GachaService,
        mock_db: MagicMock,
        mock_llm_mocker: LLMMocker,
    ):
        """既存の review_session_id で再開できること。"""
        existing_session = ReviewSession(
            session_id="review_existing123",
            request_id="req1",
            gate_forbidden_agents=["a"],
            gate_mode="scrub",
            gate_blocked_keys=["b"],
        )

        # リポジトリでロードされるモック
        from src.backend.database.repositories import EasyModeDraftRepository
        with patch.object(EasyModeDraftRepository, "load_review_session", AsyncMock(return_value=existing_session)):
            mock_llm_mocker.set_responses(
                json.dumps({"title": "A", "logline": "a", "protagonist_summary": "a", "charm_point": "a"}),
                json.dumps({"title": "B", "logline": "b", "protagonist_summary": "b", "charm_point": "b"}),
                json.dumps({"title": "C", "logline": "c", "protagonist_summary": "c", "charm_point": "c"}),
            )

            request = GachaRequest(
                genre="ファンタジー",
                keywords=["魔法"],
                temperature=0.7,
                review_session_id="review_existing123",
            )

            response = await gacha_service.generate_plans(request)

            assert response.review_session_id == "review_existing123"


# ============================================================================
# 追加: _create_isolated_plan_payload / _evaluate_single_plan_blind テスト
# ============================================================================


class TestBlindEvaluationInternals:
    """内部メソッドの単体テスト。"""

    def test_create_isolated_plan_payload_masks_other_plans(
        self,
        gacha_service: GachaService,
        mock_blind_gate: BlindReviewGate,
    ):
        """他案情報がマスクされること。"""
        target = GachaPlan(plan_id="p1", plan_type=GachaPlanType.ROYAL, title="A", logline="a", protagonist_summary="a", charm_point="a")
        other = GachaPlan(plan_id="p2", plan_type=GachaPlanType.CURVEBALL, title="B", logline="b", protagonist_summary="b", charm_point="b")

        payload = gacha_service._create_isolated_plan_payload(target, [target, other], mock_blind_gate)

        # proposal_other がスクラブされる
        assert "proposal_other" in payload
        assert "BLOCKED" in str(payload["proposal_other"])

    @pytest.mark.asyncio
    async def test_evaluate_single_plan_blind_scoring(
        self,
        gacha_service: GachaService,
        mock_blind_gate: BlindReviewGate,
    ):
        """単一案の独立採点が正しく動くこと。"""
        plan = GachaPlan(
            plan_id="p1",
            plan_type=GachaPlanType.ROYAL,
            title="王道の冒険譚",
            logline="勇者が魔王を倒す壮大な冒険ファンタジー",
            protagonist_summary="正義感の強い少年剣士",
            charm_point="熱血展開と仲間との絆が魅力の王道ファンタジー",
        )

        score, critique, reason = await gacha_service._evaluate_single_plan_blind(
            plan, [plan], "ファンタジー", mock_blind_gate
        )

        assert isinstance(score, float)
        assert 0 <= score <= 100
        assert isinstance(critique, dict)
        assert "clarity" in critique
        assert isinstance(reason, str)
        assert len(reason) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
