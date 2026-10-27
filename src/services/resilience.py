"""
services/resilience.py - オフライン／低帯域耐障害モードの状態判定

バックエンド（DB）・Gemini API の到達性を確認し、
オフライン時はセマンティックキャッシュ優先で動作するよう状態を報告する。
ネットワーク遮断時も例外を投げず、安全に offline 状態を返す。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_offline_mode_enabled() -> bool:
    """環境変数 OFFLINE_MODE でオフラインモードが有効かを返す。"""
    return os.environ.get("OFFLINE_MODE", "false").lower() in ("1", "true", "yes")


def _sync_engine_url(url: Any):
    """AsyncEngine の URL を「本当に同期接続できる」URL へ変換する。

    ``sqlite+aiosqlite://`` → ``sqlite://``、``postgresql+asyncpg://`` → ``postgresql://``。
    ``AsyncEngine.sync_engine`` は greenlet ブリッジが前提のため、
    イベントループの外から直接 ``connect()`` すると
    ``greenlet_spawn has not been called`` で必ず失敗する。
    """
    return url.set(drivername=url.get_backend_name())


def check_database() -> str:
    """DB の到達性を確認する（ok/error）。

    同期関数なので ``AsyncEngine`` もイベントループも触らない。
    URL から独立した**同期エンジン**を一時的に作って ``SELECT 1`` を実行する。

    旧実装は ``asyncio.get_event_loop().run_until_complete()`` で asyncio 奖品象眼を
    増やしていた。Python 3.14 では ``get_event_loop()`` が
    ``There is no current event loop`` を投げるため、常に "error" を返していた。
    """
    try:
        from sqlalchemy import create_engine, text

        from src.core.container import AppContainer

        mgr = AppContainer.db()
        engine = create_engine(_sync_engine_url(mgr.engine.url))
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"db check failed: {exc}")
        return "error"


def check_gemini() -> str:
    """Gemini API の到達性を確認する（ok/error）。キー未設定時は disabled。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "disabled"
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        # 軽量なモデル一覧取得で到達性を確認
        list(genai.list_models())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"gemini check failed: {exc}")
        return "error"


def get_system_status() -> dict[str, Any]:
    """システム全体の耐障害ステータスを返す。"""
    db = check_database()
    gemini = check_gemini()
    offline = is_offline_mode_enabled() or gemini == "error"
    if offline:
        mode = "offline" if is_offline_mode_enabled() else "degraded"
    else:
        mode = "online"
    return {
        "mode": mode,
        "offline_mode_enabled": is_offline_mode_enabled(),
        "database": db,
        "gemini": gemini,
        "cache_first": offline,
        "recommendation": (
            "オフライン: セマンティックキャッシュからの再開を推奨"
            if offline
            else "オンライン: 通常通り生成可能"
        ),
    }
