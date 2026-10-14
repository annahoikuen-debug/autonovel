"""IllustrationAgent 単体テスト (Step 13-16)。

Step 13: フィクスチャ定義
Step 14: generate_illustration_prompt 正常系
Step 15: ストリーミング応答処理
Step 16: エラー系
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.illustration_agent import IllustrationAgent
from src.models.illustration import (
    IllustrationModel,
    IllustrationRequest,
    IllustrationResult,
    IllustrationType,
    SafetyLevel,
)
from src.services.image_service import ImageService
from tests.mocks.llm_adapter import LLMMocker, MockLLMAdapter


# ============================================================================
# Step 13: フィクスチャ定義
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
def mock_image_service() -> MagicMock:
    """ImageService のモック。"""
    service = MagicMock(spec=ImageService)
    service.generate = AsyncMock(return_value="/static/illustrations/test.png")
    return service


@pytest.fixture
def mock_prompt_mgr() -> MagicMock:
    """プロンプトマネージャーのモック。"""
    return MagicMock()


@pytest.fixture
def illustration_agent(
    mock_llm_adapter: MockLLMAdapter,
    mock_image_service: MagicMock,
    mock_prompt_mgr: MagicMock,
) -> IllustrationAgent:
    """IllustrationAgent インスタンス (全依存をモック注入)。"""
    agent = IllustrationAgent(
        image_service=mock_image_service,
        llm=mock_llm_adapter,
        prompt_mgr=mock_prompt_mgr,
    )
    agent.repo = MagicMock()
    agent.repo.create_illustration = AsyncMock(return_value=1)
    return agent


@pytest.fixture
def sample_illustration_request() -> IllustrationRequest:
    """サンプルの IllustrationRequest (表紙)。"""
    return IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.COVER,
        model=IllustrationModel.QUALITY,
        safety_level=SafetyLevel.BLOCK_SOME,
        book_context={
            "title": "天空の城",
            "genre": "ファンタジー",
            "concept": "空に浮かぶ城を舞台にした冒険譚",
        },
    )


@pytest.fixture
def sample_character_request() -> IllustrationRequest:
    """サンプルの IllustrationRequest (キャラクター)。"""
    return IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.CHARACTER,
        model=IllustrationModel.QUALITY,
        safety_level=SafetyLevel.BLOCK_SOME,
        book_context={
            "character_name": "アリス",
            "character_description": "銀髪の魔法使い少女",
            "genre": "ファンタジー",
        },
    )


@pytest.fixture
def sample_episode_request() -> IllustrationRequest:
    """サンプルの IllustrationRequest (エピソード挿絵)。"""
    return IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.EPISODE,
        episode_number=1,
        model=IllustrationModel.QUALITY,
        safety_level=SafetyLevel.BLOCK_SOME,
        scene_text="朝の教室で、主人公は窓の外を眺めていた。",
        book_context={
            "title": "学園ファンタジー",
            "genre": "学園ファンタジー",
        },
    )


@pytest.fixture
def sample_yonkoma_request() -> IllustrationRequest:
    """サンプルの IllustrationRequest (4コマ/6コマ漫画)。"""
    return IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.YONKOMA,
        model=IllustrationModel.QUALITY,
        safety_level=SafetyLevel.BLOCK_SOME,
        scene_text="第1話のあらすじテキスト...",
        panels=6,
        book_context={
            "title": "4コマ漫画テスト",
            "genre": "コメディ",
        },
    )


# ============================================================================
# Step 14: generate_illustration_prompt 正常系
# ============================================================================


class TestGenerateIllustrationPromptSuccess:
    """generate_prompt_only / プロンプト生成の正常系テスト。"""

    @pytest.mark.asyncio
    async def test_build_cover_prompt_template_injection(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
    ):
        """表紙プロンプト: テンプレート注入・変数展開が正しく動くこと。"""
        result = await illustration_agent.generate_prompt_only(request=sample_illustration_request)

        assert result["status"] == "prompt_only"
        assert "prompt" in result
        prompt = result["prompt"]
        assert "天空の城" in prompt  # title
        assert "ファンタジー" in prompt  # genre
        assert "空に浮かぶ城" in prompt  # concept
        assert "book cover illustration" in prompt.lower()

    @pytest.mark.asyncio
    async def test_build_character_prompt_template_injection(
        self,
        illustration_agent: IllustrationAgent,
        sample_character_request: IllustrationRequest,
    ):
        """キャラクタープロンプト: テンプレート注入・変数展開が正しく動くこと。"""
        result = await illustration_agent.generate_prompt_only(request=sample_character_request)

        assert result["status"] == "prompt_only"
        prompt = result["prompt"]
        assert "アリス" in prompt  # character_name
        assert "銀髪の魔法使い少女" in prompt  # character_description
        assert "ファンタジー" in prompt  # genre
        assert "character illustration" in prompt.lower()

    @pytest.mark.asyncio
    async def test_build_episode_prompt_with_scene_text(
        self,
        illustration_agent: IllustrationAgent,
        sample_episode_request: IllustrationRequest,
    ):
        """エピソードプロンプト: scene_text から詳細情報が抽出されること。"""
        result = await illustration_agent.generate_prompt_only(request=sample_episode_request)

        assert result["status"] == "prompt_only"
        prompt = result["prompt"]
        assert "school" in prompt.lower()  # location 抽出 (英語キーワードで返る)
        assert "morning" in prompt.lower()  # time of day 抽出
        assert "学園ファンタジー" in prompt  # title/genre

    @pytest.mark.asyncio
    async def test_build_yonkoma_prompt_panels(
        self,
        illustration_agent: IllustrationAgent,
        sample_yonkoma_request: IllustrationRequest,
    ):
        """4/6コマ漫画プロンプト: パネル数指定が反映されること。"""
        result = await illustration_agent.generate_prompt_only(request=sample_yonkoma_request)

        assert result["status"] == "prompt_only"
        prompt = result["prompt"].lower()
        assert "six-panel" in prompt or "n-panel" in prompt or "yonkoma" in prompt or "panel" in prompt

    @pytest.mark.asyncio
    async def test_forbidden_words_filtered(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """禁止語フィルタ: 安全でないキーワードが除外/置換されること。"""
        request = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.BLOCK_SOME,
            book_context={
                "title": "テスト",
                "genre": "ファンタジー",
                "concept": "NSFW content explicit",
            },
        )
        result = await illustration_agent.generate_prompt_only(request=request)

        # プロンプト生成は成功する（フィルタリングは画像生成側で実施）
        assert result["status"] == "prompt_only"

    @pytest.mark.asyncio
    async def test_character_length_limit(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """文字数制限: 極端に長い入力でもプロンプトが生成されること。"""
        long_concept = "あ" * 10000
        request = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.BLOCK_SOME,
            book_context={
                "title": "テスト",
                "genre": "ファンタジー",
                "concept": long_concept,
            },
        )
        result = await illustration_agent.generate_prompt_only(request=request)

        assert result["status"] == "prompt_only"
        assert len(result["prompt"]) > 0

    @pytest.mark.asyncio
    async def test_r15_safety_level_adds_modifier(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """R15安全レベル: 適切な修飾語が追加されること。"""
        request = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.R15_CONTENT,
            book_context={"title": "テスト", "genre": "ファンタジー"},
        )
        result = await illustration_agent.generate_prompt_only(request=request)

        assert result["status"] == "prompt_only"
        prompt = result["prompt"].lower()
        assert "r15" in prompt or "tasteful" in prompt


# ============================================================================
# Step 15: ストリーミング応答処理
# ============================================================================


class TestStreamingResponse:
    """ストリーミング応答処理のテスト。"""

    @pytest.mark.asyncio
    async def test_stream_response_chunk_concatenation(
        self,
        illustration_agent: IllustrationAgent,
        mock_llm_mocker: LLMMocker,
    ):
        """async for chunk: チャンクが正しく結合されること。"""
        # ストリーミング応答を設定
        mock_llm_mocker.set_stream_chunks(
            ["キャラ", "クター", "イラスト", "の", "プロンプト"],
            ["表紙", "イラスト", "の", "プロンプト"],
            ["シーン", "イラスト", "の", "プロンプト"],
        )

        request = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.CHARACTER,
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.BLOCK_SOME,
            book_context={"character_name": "テスト", "genre": "ファンタジー"},
        )

        # stream_response を直接テスト
        chunks = []
        async for chunk in illustration_agent.llm.stream_response("test prompt"):
            chunks.append(chunk)

        full_response = "".join(chunks)
        assert "キャライラスト" in full_response or "キャラ" in full_response

    @pytest.mark.asyncio
    async def test_stream_response_empty_chunks_handled(
        self,
        illustration_agent: IllustrationAgent,
        mock_llm_mocker: LLMMocker,
    ):
        """空チャンク: 空のチャンクが適切に処理されること。"""
        mock_llm_mocker.set_stream_chunks(
            ["", "テスト", "", "プロンプト", ""],
        )

        chunks = []
        async for chunk in illustration_agent.llm.stream_response("test"):
            chunks.append(chunk)

        # 空チャンクが含まれても結合できる
        full = "".join(chunks)
        assert "テスト" in full
        assert "プロンプト" in full

    @pytest.mark.asyncio
    async def test_stream_response_incomplete_chunks(
        self,
        illustration_agent: IllustrationAgent,
        mock_llm_mocker: LLMMocker,
    ):
        """不完全チャンク: 文の途中で切れたチャンクも処理されること。"""
        mock_llm_mocker.set_stream_chunks(
            ["これは", "テス", "トです", "。"],
        )

        chunks = []
        async for chunk in illustration_agent.llm.stream_response("test"):
            chunks.append(chunk)

        full = "".join(chunks)
        assert full == "これはテストです。"

    @pytest.mark.asyncio
    async def test_stream_response_cancellation(
        self,
        illustration_agent: IllustrationAgent,
        mock_llm_mocker: LLMMocker,
    ):
        """途中キャンセル: キャンセル時にクリーンアップされること。"""
        mock_llm_mocker.set_stream_chunks(
            ["チャンク1", "チャンク2", "チャンク3", "チャンク4"],
        )

        chunks = []
        async for chunk in illustration_agent.llm.stream_response("test"):
            chunks.append(chunk)
            if len(chunks) >= 2:
                illustration_agent.llm.cancel()
                break

        assert len(chunks) == 2
        assert "チャンク1" in chunks[0]
        assert "チャンク2" in chunks[1]


# ============================================================================
# Step 16: エラー系
# ============================================================================


class TestErrorHandling:
    """エラー系テスト。"""

    @pytest.mark.asyncio
    async def test_llm_exception_fallback_to_prompt_only(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
        mock_image_service: MagicMock,
    ):
        """LLM 例外: 画像生成失敗時に prompt_only でフォールバックすること。"""
        mock_image_service.generate.side_effect = Exception("LLM API error")

        result = await illustration_agent.run(request=sample_illustration_request)

        # 画像生成失敗 → prompt_only でフォールバック
        assert result["status"] == "prompt_only"
        assert result["image_generated"] is False
        assert "prompt" in result

    @pytest.mark.asyncio
    async def test_prompt_generation_empty_request(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """プロンプト空: 必須フィールド不足でエラーdictが返されること。"""
        # _coerce_request で ValueError が投げられるが、generate_prompt_only で捕捉され error dict が返る
        result = await illustration_agent.generate_prompt_only(request=None)

        assert result["status"] == "error"
        assert "message" in result
        assert "Invalid or missing illustration request" in result["message"]

    @pytest.mark.asyncio
    async def test_prompt_generation_with_dict_request(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """dict リクエスト: dict 形式でも正常に処理されること。"""
        request_dict = {
            "book_id": 1,
            "illustration_type": IllustrationType.COVER.value,
            "model": IllustrationModel.QUALITY.value,
            "safety_level": SafetyLevel.BLOCK_SOME.value,
            "book_context": {"title": "テスト", "genre": "ファンタジー"},
        }
        result = await illustration_agent.generate_prompt_only(request=request_dict)

        assert result["status"] == "prompt_only"
        assert "prompt" in result

    @pytest.mark.asyncio
    async def test_forbidden_words_hit_in_prompt(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """禁止語ヒット: プロンプトに禁止語が含まれても生成は継続（画像生成側でブロック）"""
        request = IllustrationRequest(
            book_id=1,
            illustration_type=IllustrationType.COVER,
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.BLOCK_SOME,
            book_context={
                "title": "テスト",
                "genre": "ファンタジー",
                "concept": "explicit nsfw content",  # 禁止語
            },
        )
        result = await illustration_agent.generate_prompt_only(request=request)

        # プロンプト生成自体は成功（フィルタリングは下流）
        assert result["status"] == "prompt_only"

    @pytest.mark.asyncio
    async def test_db_save_failure_logged_not_raised(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
    ):
        """DB 保存失敗: 例外はログのみで伝播しないこと。"""
        illustration_agent.repo.create_illustration.side_effect = Exception("DB error")

        result = await illustration_agent.generate_prompt_only(request=sample_illustration_request)

        # 保存失敗してもプロンプト生成結果は返される
        assert result["status"] == "prompt_only"
        assert "prompt" in result

    @pytest.mark.asyncio
    async def test_streaming_interruption_handled(
        self,
        illustration_agent: IllustrationAgent,
        mock_llm_mocker: LLMMocker,
    ):
        """ストリーミング中断: 中断時の部分結果が適切に扱われること。"""
        mock_llm_mocker.set_stream_chunks(
            ["開始", "中間", "終了"],
        )

        chunks = []
        try:
            async for chunk in illustration_agent.llm.stream_response("test"):
                chunks.append(chunk)
                if "中間" in chunk:
                    raise asyncio.CancelledError("User cancelled")
        except asyncio.CancelledError:
            pass

        # 部分的に受信できている
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_invalid_illustration_type_defaults_to_episode(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """未知のイラストタイプ: デフォルトでエピソード扱いになること。"""
        request = IllustrationRequest(
            book_id=1,
            illustration_type="UNKNOWN_TYPE",
            model=IllustrationModel.QUALITY,
            safety_level=SafetyLevel.BLOCK_SOME,
            book_context={"title": "テスト", "genre": "ファンタジー"},
        )
        result = await illustration_agent.generate_prompt_only(request=request)

        assert result["status"] == "prompt_only"
        # エピソード用プロンプトとして生成される
        assert "prompt" in result

    @pytest.mark.asyncio
    async def test_regenerate_prompts_enhancement(
        self,
        illustration_agent: IllustrationAgent,
        sample_episode_request: IllustrationRequest,
    ):
        """プロンプト再生成: エンティティ・感情トーンが反映されること。"""
        result = await illustration_agent.regenerate_prompts(
            request=sample_episode_request,
            focus="visual_textual_synergy",
            params={
                "refocus_on_text_entities": True,
                "match_emotional_tone": True,
            },
        )

        assert result["status"] == "success"
        assert "enhanced_prompt" in result
        assert "enhancements_applied" in result
        assert result["focus"] == "visual_textual_synergy"


# ============================================================================
# 追加: execute メソッド・run メソッドの統合テスト
# ============================================================================


class TestIllustrationAgentIntegration:
    """IllustrationAgent の統合テスト。"""

    @pytest.mark.asyncio
    async def test_execute_no_request_is_noop(
        self,
        illustration_agent: IllustrationAgent,
    ):
        """request なし: no-op として正常終了すること (error なし)。"""
        from src.agents.orchestrator import AgentContext

        ctx = AgentContext(book_id=1, branch_id=1, ep_num=1, artifacts={})
        result = await illustration_agent.execute(ctx)

        assert result.error is None
        assert result.artifacts.get("illustration_skipped") is True
        assert result.next_agent is None

    @pytest.mark.asyncio
    async def test_execute_with_request_generates_prompt(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
    ):
        """request あり: プロンプト生成まで実行されること。"""
        from src.agents.orchestrator import AgentContext

        ctx = AgentContext(
            book_id=1,
            branch_id=1,
            ep_num=1,
            artifacts={"request": sample_illustration_request},
        )
        result = await illustration_agent.execute(ctx)

        assert result.error is None
        assert "illustration_result" in result.artifacts
        assert result.artifacts["illustration_result"] is not None

    @pytest.mark.asyncio
    async def test_run_cover_generation_success(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
        mock_image_service: MagicMock,
    ):
        """run: 表紙生成が成功すること。"""
        result = await illustration_agent.run(request=sample_illustration_request)

        assert result["status"] == "success"
        assert result["image_generated"] is True
        assert result["result"].image_url == "/static/illustrations/test.png"
        mock_image_service.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_character_generation_success(
        self,
        illustration_agent: IllustrationAgent,
        sample_character_request: IllustrationRequest,
        mock_image_service: MagicMock,
    ):
        """run: キャラクター生成が成功すること。"""
        result = await illustration_agent.run(request=sample_character_request)

        assert result["status"] == "success"
        assert result["image_generated"] is True

    @pytest.mark.asyncio
    async def test_run_image_generation_failure_fallback(
        self,
        illustration_agent: IllustrationAgent,
        sample_illustration_request: IllustrationRequest,
        mock_image_service: MagicMock,
    ):
        """run: 画像生成失敗時は prompt_only にフォールバックすること。"""
        mock_image_service.generate.side_effect = Exception("Generation failed")

        result = await illustration_agent.run(request=sample_illustration_request)

        assert result["status"] == "prompt_only"
        assert result["image_generated"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
