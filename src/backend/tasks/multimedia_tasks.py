"""src/backend/tasks/multimedia_tasks.py - Huey tasks for Audio & Multimedia generation (Step 18)."""

from __future__ import annotations

import logging
from typing import Any

from src.backend.tasks.huey import huey

logger = logging.getLogger(__name__)


@huey.task(retries=2, retry_delay=10)
def generate_asset_pack_task(
    book_id: int,
    task_id: str | None = None,
    include_if_routes: bool = True,
    include_media_mix: bool = True,
    include_ebook: bool = True,
    include_audio: bool = True,
    ebook_formats: list[str] = ["epub", "pdf"],
    media_mix_formats: list[str] = ["manga"],
) -> dict[str, Any]:
    """Asset Pack 生成 Huey タスク。"""
    from src.backend.multimedia_service import MultimediaService

    service = MultimediaService()
    try:
        result, task_id = service.generate_asset_pack(
            book_id=book_id,
            include_if_routes=include_if_routes,
            include_media_mix=include_media_mix,
            include_ebook=include_ebook,
            include_audio=include_audio,
            ebook_formats=ebook_formats,
            media_mix_formats=media_mix_formats,
        )

        return {
            "task_id": task_id,
            "asset_id": result.asset_id,
            "files": result.files,
            "metadata": result.metadata,
            "file_count": len(result.files),
        }
    except Exception as exc:
        logger.warning(f"generate_asset_pack_task failed for book {book_id}: {exc}")
        return {
            "task_id": task_id,
            "error": str(exc),
            "file_count": 0,
        }


@huey.task(retries=2, retry_delay=10)
def synthesize_chapter_audio_task(
    book_id: int,
    episode_num: int,
    chapter_text: str | None = None,
    characters: list[str] | None = None,
) -> dict[str, Any]:
    """指定章の音声合成 Huey タスク (Step 19)。

    直接呼び出し時も ``huey.api.Result`` (``.id`` 持ち) が返るため、
    ルータ側で ``getattr(task, "id", ...)`` として利用できる。
    """
    import asyncio as _asyncio

    from src.integrations.audio.chapter_synthesizer import ChapterAudioSynthesizer

    text = chapter_text or ""

    async def _run() -> Any:
        synthesizer = ChapterAudioSynthesizer()
        return await synthesizer.synthesize_chapter(
            book_id=book_id,
            episode_num=episode_num,
            chapter_text=text,
            characters=characters,
        )

    try:
        result = _asyncio.run(_run())
        return {
            "task_id": str(episode_num),
            "asset_id": 0,
            "file_path": result.get("file_path", ""),
            "metadata": result,
        }
    except Exception as exc:
        logger.warning(
            "synthesize_chapter_audio_task failed for book %s episode %s: %s",
            book_id,
            episode_num,
            exc,
        )
        return {"task_id": str(episode_num), "error": str(exc)}
