import logging
import os
from typing import Any

from src.shared.utils import StatusReporter

from .base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)

#: 投機実行の最低監査スコアの既定値。
_DEFAULT_MIN_AUDIT_SCORE = 90.0


def _is_truthy_env(name: str, default: str = "0") -> bool:
    raw = os.environ.get(name, default).strip().lower()
    return raw in ("1", "true", "yes", "on")


def should_speculate(last_audit_score: float | None, auto_mode: bool) -> bool:
    """投機的プリフェッチを実行してよいかを判定する（純関数 / PLAN_W6 Step 11）。

    従来は「常に次の3話分」を無条件に走らせていたため、リテイク実績が高くても
    無駄な課金が起きていた。判定材料が乏しい場合は必ず False（安全側の既定）。
    """
    if not _is_truthy_env("ENABLE_SPECULATIVE_PREFETCH", "0"):
        return False
    if not auto_mode:
        return False
    if last_audit_score is None:
        return False
    try:
        threshold = float(os.environ.get("PREFETCH_MIN_AUDIT_SCORE", "90.0"))
    except (TypeError, ValueError):
        threshold = _DEFAULT_MIN_AUDIT_SCORE
    try:
        return float(last_audit_score) >= threshold
    except (TypeError, ValueError):
        return False


class EpisodeWritingWorkflow(BaseWorkflow):
    """執筆ワークフロー: 通常モードとパイプラインモードの切り替えを隠蔽"""

    async def execute(self, reporter: StatusReporter, **kwargs) -> dict[str, Any]:
        book_id = kwargs["book_id"]
        write_from = kwargs["write_from"]
        write_to = kwargs["write_to"]
        passion = kwargs["passion"]
        word_count = kwargs["word_count"]
        do_refine = kwargs["do_refine"]
        env_state = kwargs["env_state"]
        pipeline_mode = kwargs["pipeline_mode"]
        mode = kwargs.get("mode", "final")

        # WritingService を使用（engine.writer から移行済）
        writing = self.writing

        if pipeline_mode:
            chars_count, failed = await writing.generate_episodes_pipeline(
                book_id, write_from, write_to, passion, word_count, reporter=reporter, mode=mode
            )
            # 執筆完了後にプリフェッチを実行して次のエピソード生成を高速化
            await self._trigger_prefetch(book_id, write_to, reporter)
            # 非同期で監査を走らせる (Shadow Mode)
            try:
                from src.backend.tasks import enqueue_audit_after_write

                enqueue_audit_after_write(book_id, write_from, write_to)
                reporter.report(
                    "⚖️ 非同期の論理監査タスク (Shadow Mode) をエンキューしました。", "info"
                )
            except Exception as e:
                logger.error(f"Failed to enqueue shadow audit: {e}")
            return {"chars_count": chars_count, "failed_episodes": failed, "book_id": book_id}
        else:
            chars_count = await writing.generate_episodes(
                book_id,
                write_from,
                write_to,
                passion,
                word_count,
                do_refine,
                reporter=reporter,
                env_state=env_state,
                mode=mode,
            )
            # 執筆完了後にプリフェッチを実行して次のエピソード生成を高速化
            await self._trigger_prefetch(book_id, write_to, reporter)
            # 非同期で監査を走らせる (Shadow Mode)
            try:
                from src.backend.tasks import enqueue_audit_after_write

                enqueue_audit_after_write(book_id, write_from, write_to)
                reporter.report(
                    "⚖️ 非同期の論理監査タスク (Shadow Mode) をエンキューしました。", "info"
                )
            except Exception as e:
                logger.error(f"Failed to enqueue shadow audit: {e}")
            return {"chars_count": chars_count, "book_id": book_id}

    async def _trigger_prefetch(
        self, book_id: int, last_episode: int, reporter: StatusReporter
    ) -> None:
        """
        執筆完了後に Semantic Cache のプリフェッチ機能を起動し、
        次のエピソード群のEmbeddingを先行計算してキャッシュをウォームアップする。

        PLAN_W6 Step 8:
        - `SemanticCacheManager` を **毎回作り直さず** インスタンス単位で使い回す
          （L1=1000件 / L2-B=500件 が毎回ゼロからになる構造的欠陥の解消）。
        - `asyncio.create_task` の **戻り値ハンドルを `self._prefetch_tasks` に保持**する
          （handle-less タスクはリテイク時に殺せない）。
        - 新たな投機処理は書かない。`prefetch_by_pattern` は Step 4 で既定 OFF。
        - Step 11: 投機は「高確度かつ自動モード」のときだけ（既定では走らない）。
        """
        if not should_speculate(
            getattr(self, "last_audit_score", None), bool(getattr(self, "auto_mode", False))
        ):
            logger.debug("[PREFETCH] Speculative prefetch is not allowed; skipping")
            return
        try:
            from src.services.semantic_cache import SemanticCacheManager

            # SemanticCacheManager のインスタンスを取得
            # (Container 等でインジェクションされている場合はそれを使用)
            vector_store = getattr(self, "vector_store", None)
            client = getattr(self, "llm_client", None) or getattr(self, "client", None)

            if not vector_store or not client:
                # VectorStore/Client が注入されていない場合はスキップ
                logger.debug("[PREFETCH] VectorStore or Client not available, skipping prefetch")
                return

            # 初回だけ生成して使い回す（ウォームアップの効果を構造的に残す）
            cache_manager = getattr(self, "_semantic_cache", None)
            if cache_manager is None:
                cache_manager = SemanticCacheManager(vector_store=vector_store, client=client)
                self._semantic_cache = cache_manager

            # 次の3エピソード分のプリフェッチを非同期実行
            prefetch_task_types = ["drafting", "polishing"]
            next_ep = last_episode + 1

            # バックグラウンドでプリフェッチを実行（執筆をブロックしない）
            import asyncio

            task = asyncio.create_task(
                cache_manager.prefetch_by_pattern(
                    book_id=book_id,
                    ep_range_start=next_ep,
                    ep_range_end=min(next_ep + 2, next_ep + 3),  # 次の3話まで
                    task_types=prefetch_task_types,
                )
            )
            # ハンドルを保持する（リテイク / 停止時に殺せるようにする）
            prefetch_tasks = getattr(self, "_prefetch_tasks", None)
            if prefetch_tasks is None:
                prefetch_tasks = set()
                self._prefetch_tasks = prefetch_tasks
            prefetch_tasks.add(task)
            task.add_done_callback(prefetch_tasks.discard)

            reporter.report(
                f"🚀 Prefetch triggered for ep{next_ep}-ep{next_ep + 2} (background)", "debug"
            )
            logger.info(f"[PREFETCH] Triggered for book_id={book_id}, ep{next_ep}-ep{next_ep + 2}")
        except Exception as e:
            # プリフェッチ失敗は致命的なエラーではなくログ出力のみ
            logger.warning(f"[PREFETCH] Prefetch trigger failed: {e}")
