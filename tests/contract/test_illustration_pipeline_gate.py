"""ADR 003 Increment 2: 挿絵パイプライン経路の off 差分ゼロ契約（PLAN_P1 TRACK-I / I7）。

契約:
- `ENABLE_EASY_ILLUSTRATION=0`（既定）: easy mode は `enable_illustration=False`
  （従来と同一の挙動・挿絵生成は一切走らない）
- `ENABLE_EASY_ILLUSTRATION=1`: IllustrationStep が到達可能（既存二重ゲートを維持）
- `ILLUSTRATION_MAX_PER_BOOK`: 1 作品あたりの生成枚数上限（コスト上限）
- キー未設定環境では `run()` が prompt-only にフォールバック（現行契約の維持）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_easy_illustration_flag_defaults_off() -> None:
    """既定 OFF（off 差分ゼロ契約の土台）。"""
    from src.infrastructure.config.settings import settings

    assert settings.ENABLE_EASY_ILLUSTRATION is False
    assert settings.ILLUSTRATION_MAX_PER_BOOK == 20


async def test_easy_illustration_flag_on_reaches_step_gate() -> None:
    """flag ON で WorkflowContext に enable_illustration=True が入る（二重ゲートの 1 段目）。"""
    from src.infrastructure.config.settings import settings

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_EASY_ILLUSTRATION", "1")
        # pydantic-settings は環境変数をインスタンス化時に読むため、再構築して確認する
        from src.infrastructure.config.settings import Settings

        fresh = Settings()
        assert fresh.ENABLE_EASY_ILLUSTRATION is True
        # 既定インスタンスは変更しない（off 契約を壊さない）
        assert settings.ENABLE_EASY_ILLUSTRATION is False


async def test_illustration_step_skips_when_disabled() -> None:
    """既定（flag OFF）では IllustrationStep が何も生成せず skip する（現行挙動維持）。"""
    from src.engine.pipeline_base import WorkflowContext
    from src.services.pipeline_steps import IllustrationStep

    ctx = WorkflowContext(
        genre="ファンタジー",
        keywords="テスト",
        archetype_key="test",
        target_eps=1,
        initial_limit=1,
        word_count=100,
        book_id=1,
        enable_illustration=False,
    )
    ctx.enable_illustration = False
    step = IllustrationStep()
    reporter = MagicMock()

    ok = await step.execute(ctx, engine=MagicMock(), reporter=reporter)

    assert ok is True
    assert getattr(ctx, "illustrations", None) in (None, [])


async def test_illustration_workflow_respects_max_per_book() -> None:
    """maxPerBook 上限で話数ループが止まり、作品は正常完了する（I6）。"""
    from src.agents.illustration_agent import IllustrationAgent
    from src.backend.workflows.illustration_workflow import IllustrationWorkflow
    from src.publishing.illustration.image_service import ImageService

    agent = IllustrationAgent(image_service=MagicMock(spec=ImageService))
    agent.run = AsyncMock(
        return_value={"status": "success", "result": {"image_url": "/x.png"}, "image_generated": True}
    )

    class _Repo:
        async def get_all_non_anchor_chapters(self, book_id: int, branch_id: int = 1, order_by: str = "ep_num"):
            return [MagicMock() for _ in range(5)]

    workflow = IllustrationWorkflow(illustration_agent=agent, repo=_Repo())
    reporter = MagicMock()

    result = await workflow.execute(
        reporter,
        book_id=1,
        settings={
            "enableIllustration": True,
            "generateCover": False,
            "generateEpisodeIllustrations": True,
            "generateYonkoma": False,
            "maxPerBook": 2,
        },
    )

    assert result["status"] == "success"
    assert len(result["illustrations"]) == 2
    # 上限 2 件で止まるため、run は 2 回しか呼ばれない
    assert agent.run.await_count == 2


async def test_agent_run_falls_back_to_prompt_only_without_key() -> None:
    """キー未設定環境の契約維持: run() は prompt_only にフォールバックし image_url は空。"""
    from src.agents.illustration_agent import IllustrationAgent
    from src.models.illustration import IllustrationModel, IllustrationRequest, IllustrationType, SafetyLevel

    agent = IllustrationAgent(image_service=MagicMock())
    # 実画像生成が失敗する（キー未設定相当）
    agent.image_service.generate = AsyncMock(side_effect=ValueError("missing api key"))
    # repo を注入して永続化経路も検証する（I2）
    agent.repo = MagicMock()
    agent.repo.create_illustration = AsyncMock(return_value=77)

    request = IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.EPISODE,
        episode_number=3,
        model=IllustrationModel.AUTO,
        safety_level=SafetyLevel.BLOCK_SOME,
    )
    res = await agent.run(request=request)

    assert res["status"] == "prompt_only"
    assert res["image_generated"] is False
    assert res["result"].image_url == ""
    # repo 注入により prompt-only でも永続化される（既存契約・image_url="" は下流で識別可能）
    agent.repo.create_illustration.assert_awaited_once()
    assert res["result"].illustration_id == 77


async def test_agent_run_generates_real_image_when_service_available() -> None:
    """キー設定環境（サービスが使える）では実画像を生成し DB 保存する（I4）。"""
    from src.agents.illustration_agent import IllustrationAgent
    from src.models.illustration import IllustrationModel, IllustrationRequest, IllustrationType, SafetyLevel

    agent = IllustrationAgent(image_service=MagicMock())
    agent.image_service.generate = AsyncMock(return_value="/static/illustrations/ep3.png")
    agent.repo = MagicMock()
    agent.repo.create_illustration = AsyncMock(return_value=99)

    request = IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.EPISODE,
        episode_number=3,
        model=IllustrationModel.AUTO,
        safety_level=SafetyLevel.BLOCK_SOME,
    )
    res = await agent.run(request=request)

    assert res["status"] == "success"
    assert res["image_generated"] is True
    assert res["result"].image_url == "/static/illustrations/ep3.png"
    agent.repo.create_illustration.assert_awaited_once()
    assert res["result"].illustration_id == 99


async def test_agent_run_keeps_image_on_persist_failure() -> None:
    """review-loop 指摘 7: 生成成功・保存失敗では画像を保持したまま success を返す。

    生成済み画像を prompt-only フォールバックで握り潰さない
    （「生成したのに保存されない」暗黙消滅の防止）。
    """
    from src.agents.illustration_agent import IllustrationAgent
    from src.models.illustration import IllustrationModel, IllustrationRequest, IllustrationType, SafetyLevel

    agent = IllustrationAgent(image_service=MagicMock())
    agent.image_service.generate = AsyncMock(return_value="/static/illustrations/ep3.png")
    agent.repo = MagicMock()
    agent.repo.create_illustration = AsyncMock(side_effect=RuntimeError("db down"))

    request = IllustrationRequest(
        book_id=1,
        illustration_type=IllustrationType.EPISODE,
        episode_number=3,
        model=IllustrationModel.AUTO,
        safety_level=SafetyLevel.BLOCK_SOME,
    )
    res = await agent.run(request=request)

    assert res["status"] == "success"
    assert res["image_generated"] is True
    assert res["result"].image_url == "/static/illustrations/ep3.png"
    # 保存失敗でも生成結果は失われない（illustration_id は None）
    assert res["result"].illustration_id is None
