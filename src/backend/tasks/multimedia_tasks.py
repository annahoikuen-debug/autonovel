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
            "file_count": len(result.files)
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
    chapter_text: str,
    characters: list[str] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """章テキストから音声を合成し AudioAssetModel を作成する Huey タスク。"""
    import asyncio
    import struct

    from src.backend.database import SessionLocal
    from src.backend.database.models import AudioAssetModel
    from src.backend.multimedia_storage import ensure_multimedia_dir
    from src.services.audio.base import AudioSynthesisRequest
    from src.services.audio.dialogue_extractor import DialogueExtractor
    from src.services.audio.factory import get_audio_client
    from src.services.audio.speaker_mapper import assign_speaker_id

    out_dir = ensure_multimedia_dir() / f"book_{book_id}" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ep{episode_num:03d}.wav"

    try:
        extractor = DialogueExtractor()
        lines = extractor.extract_lines(chapter_text, characters=characters or [])
        client = get_audio_client()

        audio_chunks: list[bytes] = []
        total_duration = 0.0

        for line in lines:
            speaker_id = assign_speaker_id(line.speaker_name or "narration")
            req = AudioSynthesisRequest(text=line.text, speaker_id=speaker_id)
            if asyncio.iscoroutinefunction(client.synthesize):
                res = asyncio.run(client.synthesize(req))
            else:
                res = client.synthesize(req)
                if asyncio.iscoroutine(res):
                    res = asyncio.run(res)
            if res and res.audio_bytes:
                audio_chunks.append(res.audio_bytes)
                total_duration += getattr(res, "duration_seconds", 0.0)

        if audio_chunks:
            final_bytes = audio_chunks[0]
            if len(audio_chunks) > 1:
                body = b"".join(
                    c[44:] if c.startswith(b"RIFF") and len(c) > 44 else c
                    for c in audio_chunks
                )
                header = (
                    b"RIFF"
                    + struct.pack("<I", len(body) + 36)
                    + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data"
                    + struct.pack("<I", len(body))
                )
                final_bytes = header + body
            out_path.write_bytes(final_bytes)
        else:
            from src.plugins.audio.voicevox import VoicevoxProvider

            VoicevoxProvider._write_silent_wav(str(out_path), duration_sec=1.0)
            total_duration = 1.0

        file_size = out_path.stat().st_size if out_path.exists() else 0

        with SessionLocal() as session:
            asset = AudioAssetModel(
                book_id=book_id,
                episode_num=episode_num,
                file_path=str(out_path),
                duration_seconds=total_duration,
                file_size_bytes=file_size,
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            asset_id = asset.id

        return {
            "status": "completed",
            "audio_id": asset_id,
            "book_id": book_id,
            "episode_num": episode_num,
            "file_path": str(out_path),
            "duration_seconds": total_duration,
            "file_size_bytes": file_size,
        }
    except Exception as exc:
        logger.error(
            f"synthesize_chapter_audio_task failed for book {book_id} ep {episode_num}: {exc}",
            exc_info=True,
        )
        return {
            "status": "failed",
            "error": str(exc),
            "book_id": book_id,
            "episode_num": episode_num,
        }
