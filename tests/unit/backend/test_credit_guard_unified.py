"""課金ガド統一 (unified credit guard) のテスト。

- 有償生成エンドポイントがタスク投入 (enqueue / DB 書込) の前に
  残高不足を 402 で拒否すること:
    * POST /orchestrated/generate
    * POST /api/episodes/retry_failed
    * POST /api/illustrations/batch
- 挿絵バッチ Huey タスクが失敗したときにクレジットを返金すること。
- バッチの要求枚数見積りが IllustrationWorkflow の挙動と一致すること。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _broke_user(credits: int = 0):
    from src.backend.database.models import User

    return User(
        id=7,
        email=f"broke-{credits}@example.com",
        hashed_password="x",
        display_name="broke",
        role="user",
        status="active",
        credits=credits,
    )


def _orchestrated_payload() -> dict:
    return {
        "book_id": 1,
        "branch_id": 1,
        "ep_num": 1,
        "title": "テスト作品",
        "synopsis": "テストあらすじ",
        "target_eps": 10,
        "genre": "fantasy",
    }


def test_orchestrated_generate_returns_402_when_credits_insufficient():
    """残高 0 のユーザーはタスク投入前に 402 で拒否され、 enqueue も DB 書込もされない。"""
    from src.backend.auth import get_current_user
    from src.backend.rate_limit import generate_limiter
    from src.backend.routers.orchestrated import router as orchestrated_router

    app = FastAPI()
    app.include_router(orchestrated_router)
    app.dependency_overrides[get_current_user] = lambda: _broke_user(credits=0)

    generate_limiter.reset()
    with (
        patch(
            "src.backend.routers.orchestrated.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.backend.routers.orchestrated.BookRepository") as mock_repo_cls,
        patch("src.backend.routers.orchestrated.generate_chapter_orchestrated_task") as mock_task,
    ):
        mock_repo_cls.return_value.get_book.return_value = MagicMock(user_id=7)
        client = TestClient(app)
        resp = client.post("/orchestrated/generate", json=_orchestrated_payload())

    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "INSUFFICIENT_CREDITS"
    assert detail["balance"] == 0
    # ガドは enqueue より前に走る: タスク投入もタスクレコード作成もされていないこと
    mock_task.assert_not_called()
    mock_repo_cls.return_value.create_task.assert_not_called()


def test_orchestrated_generate_null_owner_is_rejected():
    """NULL owner bypass が廃止され、owner_guard 経由で非管理者が 403 になること。

    ルーター側が `book.user_id is None` を素通ししていた旧実装の回帰防止。
    (所有権判定は owner_guard の ``verify_book_ownership`` に一本化済み)
    """
    import asyncio
    import inspect

    import pytest
    from fastapi import HTTPException

    from src.backend.database.models import Book
    from src.backend.routers.orchestrated import generate_orchestrated
    from src.backend.security.owner_guard import verify_book_ownership

    # 1) ルーターが verify_book_ownership を呼び、旧 bypass 構文が消えていること
    src = inspect.getsource(generate_orchestrated)
    assert "verify_book_ownership(" in src
    assert 'getattr(book, "user_id", None) is not None' not in src

    # 2) ガード本体は NULL owner の作品を一般ユーザーへ 403 で拒否すること
    class _DummySession:
        async def execute(self, stmt):
            class _Result:
                def scalar_one_or_none(self):
                    return Book(id=1, user_id=None, title="Orphan")

            return _Result()

    user = _broke_user(credits=100)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_book_ownership(1, user, uow=_DummySession()))
    assert exc_info.value.status_code == 403


def test_retry_failed_returns_402_when_credits_insufficient():
    """失敗リトライ (生成コスト発生) は残高検証済みでないとタスク投入されない。"""
    from src.backend.auth import get_current_user
    from src.backend.routers import episodes as episodes_module

    app = FastAPI()
    app.include_router(episodes_module.router)
    app.dependency_overrides[get_current_user] = lambda: _broke_user(credits=0)

    with (
        patch(
            "src.backend.routers.episodes.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "src.backend.routers.episodes._cancel_prefetch_for_book",
            new=AsyncMock(return_value=0),
        ) as mock_cancel,
        patch(
            "src.backend.routers.episodes._create_task",
            new=AsyncMock(return_value=None),
        ) as mock_create,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/episodes/retry_failed",
            json={"book_id": 1, "api_key": "", "passion": 1.0, "word_count": 2000},
        )

    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "INSUFFICIENT_CREDITS"
    # ガドは副作用より前に走る
    mock_cancel.assert_not_awaited()
    mock_create.assert_not_awaited()


def test_illustration_batch_returns_402_when_credits_insufficient():
    """挿絵バッチは (単価 × 予想枚数) が不足すると 402 でタスク投入されない。"""
    import src.backend.tasks.illustration_tasks as illustration_tasks
    from src.backend.auth import get_current_user
    from src.dependencies import get_illustration_workflow
    from src.backend.routers.illustrations import router as illustrations_router

    app = FastAPI()
    app.include_router(illustrations_router, prefix="/api/illustrations")
    app.dependency_overrides[get_current_user] = lambda: _broke_user(credits=4)
    app.dependency_overrides[get_illustration_workflow] = lambda: MagicMock()

    with (
        patch(
            "src.backend.routers.illustrations.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(illustration_tasks, "illustrate_batch_task") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/illustrations/batch",
            json={"book_id": 1, "settings": {"enableIllustration": True}},
        )

    # 表紙 1 枚 × COST_PER_ILLUSTRATION (5) > 4 → 402
    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "INSUFFICIENT_CREDITS"
    assert detail["required"] == 5
    assert detail["balance"] == 4
    mock_task.assert_not_called()


def test_illustration_batch_queues_when_credits_sufficient():
    """残高が要求額以上なら従来どおりキュー投入される。"""
    import src.backend.tasks.illustration_tasks as illustration_tasks
    from src.backend.auth import get_current_user
    from src.dependencies import get_illustration_workflow
    from src.backend.routers.illustrations import router as illustrations_router

    app = FastAPI()
    app.include_router(illustrations_router, prefix="/api/illustrations")
    app.dependency_overrides[get_current_user] = lambda: _broke_user(credits=5)
    app.dependency_overrides[get_illustration_workflow] = lambda: MagicMock()

    with (
        patch(
            "src.backend.routers.illustrations.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(illustration_tasks, "illustrate_batch_task") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/illustrations/batch",
            json={"book_id": 1, "settings": {"enableIllustration": True}},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    mock_task.assert_called_once()


def test_illustration_batch_disabled_skips_credit_check():
    """``enableIllustration`` 偽ならワークフローがスキップするため残高検証も不要 (0 枚)。"""
    import src.backend.tasks.illustration_tasks as illustration_tasks
    from src.backend.auth import get_current_user
    from src.dependencies import get_illustration_workflow
    from src.backend.routers.illustrations import router as illustrations_router

    app = FastAPI()
    app.include_router(illustrations_router, prefix="/api/illustrations")
    app.dependency_overrides[get_current_user] = lambda: _broke_user(credits=0)
    app.dependency_overrides[get_illustration_workflow] = lambda: MagicMock()

    with (
        patch(
            "src.backend.routers.illustrations.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(illustration_tasks, "illustrate_batch_task") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/illustrations/batch",
            json={"book_id": 1, "settings": {"enableIllustration": False}},
        )

    assert resp.status_code == 200, resp.text
    mock_task.assert_called_once()


# ============================================================================
# (b) 挿絵バッチ失敗時の返金
# ============================================================================


def test_illustration_task_refunds_credits_on_failure():
    """生成失敗時、控除済みクレジットを (user_id, 額, task_id) で返金する。"""
    import src.backend.tasks.illustration_tasks as it

    with (
        patch.object(it, "_update_task"),
        patch.object(it, "_deduct_batch_credits", return_value=(7, 5)) as mock_deduct,
        patch.object(it, "_refund_batch_credits") as mock_refund,
        patch.object(
            it,
            "_run_illustration_batch",
            new=AsyncMock(side_effect=RuntimeError("LLM 生成に失敗")),
        ),
    ):
        result = it.illustrate_batch_task.call_local(
            book_id=1,
            settings={"enableIllustration": True},
            task_id="illust_fail1",
        )

    mock_deduct.assert_called_once_with(1, {"enableIllustration": True}, "illust_fail1")
    mock_refund.assert_called_once_with(7, 5, "illust_fail1")
    assert result["status"] == "error"


def test_illustration_task_success_does_not_refund():
    """成功時はクレジットを返金しない (控除を確定させる)。"""
    import src.backend.tasks.illustration_tasks as it

    with (
        patch.object(it, "_update_task"),
        patch.object(it, "_deduct_batch_credits", return_value=(7, 5)),
        patch.object(it, "_refund_batch_credits") as mock_refund,
        patch.object(
            it,
            "_run_illustration_batch",
            new=AsyncMock(return_value={"status": "success", "illustrations": []}),
        ),
    ):
        result = it.illustrate_batch_task.call_local(
            book_id=1,
            settings={"enableIllustration": True},
            task_id="illust_ok1",
        )

    assert result["status"] == "success"
    mock_refund.assert_not_called()


def test_illustration_task_deduction_failure_fails_without_refund():
    """控除に失敗した場合は何も取っていないため返金せずタスクを失敗させる。"""
    import src.backend.tasks.illustration_tasks as it

    with (
        patch.object(it, "_update_task") as mock_update,
        patch.object(
            it,
            "_deduct_batch_credits",
            side_effect=ValueError("クレジット残高不足"),
        ),
        patch.object(it, "_refund_batch_credits") as mock_refund,
        patch.object(it, "_run_illustration_batch", new=AsyncMock()) as mock_run,
    ):
        result = it.illustrate_batch_task.call_local(
            book_id=1,
            settings={"enableIllustration": True},
            task_id="illust_broke",
        )

    assert result["status"] == "error"
    assert "Credit deduction failed" in result["message"]
    mock_refund.assert_not_called()
    mock_run.assert_not_called()
    mock_update.assert_any_call("illust_broke", "failed")


def test_illustration_task_refund_logs_and_survives_refund_error():
    """返金自体が失敗してもタスク結果は error のまま返り、例外で落ちないこと。"""
    import src.backend.tasks.illustration_tasks as it

    with (
        patch.object(it, "_update_task"),
        patch.object(it, "_deduct_batch_credits", return_value=(7, 5)),
        patch.object(it, "_refund_batch_credits", side_effect=RuntimeError("台帳書き込み失敗")),
        patch.object(it, "_run_illustration_batch", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        result = it.illustrate_batch_task.call_local(
            book_id=1,
            settings={"enableIllustration": True},
            task_id="illust_refund_err",
        )

    assert result["status"] == "error"


# ============================================================================
# バッチの要求枚数見積り
# ============================================================================


def test_estimate_illustration_batch_images():
    """IllustrationWorkflow.execute の分岐と一致する枚数見積りであること。"""
    from src.backend.tasks.illustration_tasks import estimate_illustration_batch_images

    # 設定無しならワークフローはスキップ → 0 枚
    assert estimate_illustration_batch_images(None) == 0
    assert estimate_illustration_batch_images({}) == 0
    assert estimate_illustration_batch_images({"enableIllustration": False}) == 0
    # 有効 + 表紙 (デフォルト有効) → 1 枚
    assert estimate_illustration_batch_images({"enableIllustration": True}) == 1
    # 表紙無効 + 話数挿絵 10 話 / interval 3 → ceil(10/3) = 4 枚
    assert (
        estimate_illustration_batch_images(
            {
                "enableIllustration": True,
                "generateCover": False,
                "generateEpisodeIllustrations": True,
                "episodeCount": 10,
                "episodeInterval": 3,
            }
        )
        == 4
    )
    # 明示指定は最優先
    assert estimate_illustration_batch_images({"enableIllustration": True, "imageCount": 7}) == 7
