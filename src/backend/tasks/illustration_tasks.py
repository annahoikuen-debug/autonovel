"""挿絵バッチ Huey タスク。

Issue #6: バッチエンドポイントを非同期化し、進捗を
``/api/illustrations/status/{task_id}`` で取得できるようにする。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from src.backend import database
from src.backend.database.repository import BookRepository
from src.backend.tasks.huey import huey

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _update_task(task_id: str, status: str, result_json: str | None = None) -> None:
    session = database.SessionLocal()
    try:
        repo = BookRepository(session)
        if result_json is not None:
            repo.set_task_result(task_id, result_json)
        else:
            repo.update_task_status(task_id, status)
    except Exception:
        session.rollback()
        logger.exception("Illustration task DB update failed: %s", task_id)
    finally:
        session.close()


def estimate_illustration_batch_images(settings: dict[str, Any] | None) -> int:
    """挿絵バッチの予想生成枚数を返す (課金ガド / 控除額の計算用)。

    ``IllustrationWorkflow.execute`` の挙動に合わせて見積もる:
    - ``enableIllustration`` が偽ならワークフローがスキップするため 0 枚。
    - 明示指定 (``imageCount`` / ``numImages``) があればそれを優先する。
    - 表紙 (``generateCover``、デフォルト有効) を 1 枚として加算する。
    - 話数挿絵はタスク投入時点で章数を DB 参照しないため、
      ``episodeCount`` が設定されている場合のみ ``episodeInterval`` で
      割って切り上げで加算する (不明なら表紙分のみを要求する)。
    """
    if not settings or not settings.get("enableIllustration", False):
        return 0
    for key in ("imageCount", "numImages", "image_count"):
        raw = settings.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            break
    images = 1 if settings.get("generateCover", True) else 0
    if settings.get("generateEpisodeIllustrations", False):
        try:
            episode_count = int(settings.get("episodeCount") or 0)
        except (TypeError, ValueError):
            episode_count = 0
        if episode_count > 0:
            try:
                interval = max(1, int(settings.get("episodeInterval", 3) or 3))
            except (TypeError, ValueError):
                interval = 3
            images += -(-episode_count // interval)  # 切り上げ除算
    return images


def _deduct_batch_credits(book_id: int, settings: dict | None, task_id: str) -> tuple[int, int]:
    """挿絵バッチ実行前のクレジット控除 (冪等)。

    戻り値は ``(user_id, 控除額)``。生成コストが 0 の場合は ``(0, 0)`` を返す。
    同一 ``(task_id, transaction_type)`` の控除が台帳に既にある場合は
    タスクのリトライとみなし二重控除をスキップする (``_sync_deduct_credits``
    の冪等チェックによる)。残高不足などで控除できなければ例外を送出する
    (呼び出し側でタスクを失敗させる)。
    """
    from src.backend.tasks.generation_tasks import (
        _get_user_id_from_book_id,
        _sync_deduct_credits,
    )
    from src.services.billing.credit_service import CreditService

    num_images = estimate_illustration_batch_images(settings)
    if num_images <= 0:
        return 0, 0
    cost = CreditService.COST_PER_ILLUSTRATION * num_images
    user_id = _get_user_id_from_book_id(book_id)
    _sync_deduct_credits(
        user_id=user_id,
        amount=cost,
        task_id=task_id,
        description="Illustration batch credit hold",
        transaction_type="illustration_batch",
    )
    logger.info(
        "Illustration batch credit hold: task_id=%s user_id=%s cost=%d",
        task_id,
        user_id,
        cost,
    )
    return user_id, cost


def _refund_batch_credits(user_id: int, amount: int, task_id: str) -> None:
    """失敗した挿絵バッチのクレジットを返金する (冪等・ログ出力あり)。"""
    from src.backend.tasks.generation_tasks import _sync_grant_credits

    _sync_grant_credits(
        user_id=user_id,
        amount=amount,
        task_id=task_id,
        description="Refund for failed illustration batch",
        tx_type="refund",
    )
    logger.info(
        "Refunded credits for failed illustration batch: task_id=%s user_id=%s amount=%d",
        task_id,
        user_id,
        amount,
    )


async def _run_illustration_batch(book_id: int, settings: dict) -> dict[str, Any]:
    """AppContainer 経由で IllustrationWorkflow を呼んでバッチ実行。"""
    from src.dependencies import get_illustration_workflow

    workflow = get_illustration_workflow()

    class _ReporterShim:
        def __init__(self, id: str):
            self.id = id

        def report(self, message: str, level: str = "info") -> None:
            pass

        def update_progress(self, current: int, total: int, message: str = "", sub_message: str = "") -> None:
            pass

        @property
        def state(self):
            class _S:
                def should_stop(self) -> bool:
                    return False

            return _S()

    reporter = _ReporterShim(id=f"batch_{book_id}")
    return await workflow.execute(reporter=reporter, book_id=book_id, settings=settings)


@huey.task()
def illustrate_batch_task(book_id: int, settings: dict, task_id: str | None = None) -> dict[str, Any]:
    """非同期で挿絵バッチを実行する Huey タスク。

    ``task_id`` を渡すとそれをそのまま使う。渡されない場合は従来どおり採番する。
    ルーターが即座に返す ``task_id`` とワーカーが記録する ``task_id`` が
    ずれると ``GET /status/{task_id}`` が永久に 404 になるため、
    ルーター側で採番した値を渡すのが正しい。
    """
    if not task_id:
        task_id = f"illust_{uuid.uuid4().hex[:8]}"
    logger.info("Illustration batch task started: book_id=%s task_id=%s", book_id, task_id)
    _update_task(task_id, "processing")

    # 課金: タスク開始時にクレジットを控除する (投入前の残高検証はルーター側)。
    # 同一 task_id でリトライ / リプレイされても二重控除しない (冪等)。
    user_id = 0
    credit_cost = 0
    credits_deducted = False
    try:
        user_id, credit_cost = _deduct_batch_credits(book_id, settings, task_id)
        credits_deducted = credit_cost > 0
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to deduct credits for illustration batch: %s", e)
        _update_task(task_id, "failed")
        return {"status": "error", "message": f"Credit deduction failed: {e}"}

    try:
        result = _run_async(_run_illustration_batch(book_id, settings))
        _update_task(task_id, "completed", result_json=json.dumps(result, default=str))
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("Illustration batch task failed: %s", task_id)
        _update_task(task_id, "failed")
        # 控除済みのまま失敗したクレジットを返金する (返金自体も冪等)。
        if credits_deducted and user_id:
            try:
                _refund_batch_credits(user_id, credit_cost, task_id)
            except Exception as refund_err:  # noqa: BLE001
                logger.exception("Failed to refund credits: task_id=%s error=%s", task_id, refund_err)
        return {"status": "error", "message": str(e)}


__all__ = ["illustrate_batch_task", "estimate_illustration_batch_images"]
