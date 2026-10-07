"""MarketingAgent / マーケティング関連エンドポイントのユニットテスト."""
from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.marketing import MarketingAgent

pytestmark = pytest.mark.flaky(reruns=3, reruns_delay=2)


def _make_llm(return_value):
    llm = MagicMock()
    llm.generate_json = AsyncMock(return_value=return_value)
    return llm


def _make_pm():
    pm = MagicMock()
    pm.build_marketing_pack_prompt = AsyncMock(return_value="PROMPT")
    return pm


@pytest.mark.asyncio
async def test_generate_pack_success():
    """LLM が metadata キー付き JSON を返した時に metadata dict が返る."""
    llm = _make_llm({"metadata": {"title": "テスト作品", "tags": ["A", "B"]}})
    agent = MarketingAgent(llm=llm, prompt_manager=_make_pm())

    result = await agent.generate_pack(
        book_title="テスト作品", synopsis="あらすじ", latest_ep=1
    )

    assert result == {"title": "テスト作品", "tags": ["A", "B"]}
    llm.generate_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_pack_missing_metadata_key():
    """metadata キー欠落 / 空 dict の時に safe default が返る."""
    llm = _make_llm({"title": "直接タイトル", "tags": ["x"]})
    agent = MarketingAgent(llm=llm, prompt_manager=_make_pm())

    result = await agent.generate_pack(
        book_title="元タイトル", synopsis="あらすじ", latest_ep=2
    )

    assert result["title"] == "直接タイトル"
    assert result["tags"] == ["x"]
    assert "raw" in result


@pytest.mark.asyncio
async def test_generate_pack_no_prompt_manager():
    """PromptManager 未注入でも例外を投げず fallback dict を返す."""
    llm = _make_llm({})
    agent = MarketingAgent(llm=llm, prompt_manager=None)
    agent.prompt_manager = None

    result = await agent.generate_pack(
        book_title="t", synopsis="s", latest_ep=1
    )

    assert result["title"] == "t"
    assert result["tags"] == []


@pytest.mark.asyncio
async def test_create_export_package_zip():
    """repo モックで ZIP が bytes で返り export_<id>.zip 命名."""
    book = MagicMock()
    book.id = 42
    book.title = "作品"
    book.genre = "ファンタジー"
    book.current_branch_id = 1

    chapter = MagicMock()
    chapter.ep_num = 1
    chapter.title = "第1話"
    chapter.content = "本文"

    char = MagicMock()
    char.name = "主人公"
    char.role = "主人公"
    char.registry_data = {"personality": "勇敢", "ability": "剣術"}
    char.model_dump = MagicMock(side_effect=AttributeError("no"))

    bible = MagicMock()
    bible.settings = {"world": "magic"}

    plot = MagicMock()
    plot.ep_num = 1
    plot.title = "プロット"
    plot.one_line_summary = "要約"

    repo = MagicMock()
    repo.get_book = AsyncMock(return_value=book)
    repo.get_all_non_anchor_chapters = AsyncMock(return_value=[chapter])
    repo.get_all_characters = AsyncMock(return_value=[char])
    repo.get_latest_bible = AsyncMock(return_value=bible)
    repo.get_all_plots = AsyncMock(return_value=[plot])

    agent = MarketingAgent(repo=repo, llm=_make_llm({}), prompt_manager=_make_pm())
    zip_data, zip_filename = await agent.create_export_package(42)

    assert isinstance(zip_data, bytes)
    assert zip_filename == "export_42.zip"
    assert zip_filename.startswith("export_")

    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        names = z.namelist()
        assert any("本文" in n for n in names)
        assert any("設定" in n for n in names)


def test_post_export_package_endpoint(client, real_db_manager):
    """POST /api/marketing/export_package/{id} が 200 + application/zip を返す.

    2026-10-04 の公開前監査で、このエンドポイントには IDOR が存在した
    （認証・所有権の検証が一切なく、任意の認証ユーザーが任意の book_id を
    走査して他人の作品 ZIP を一括取得できた）。所有者検証を追加したため
    検証が必須になっており、本テストは**所有を持つ作品を用意する**。
    """
    import os

    from dependency_injector import providers
    from fastapi.testclient import TestClient

    from src.backend.database.core import DatabaseManager
    from src.backend.database.models import Book, User
    from src.core.container import AppContainer

    os.environ["AUTH_DISABLED"] = "true"

    # `verify_book_ownership` は作品の実在を最初に確認する（管理者がいても 404）。
    # 開発用の autonovel.db を汚さないよう一時 SQLite に束縛し直して投入する。
    AppContainer.db.override(providers.Object(DatabaseManager(os.environ["DATABASE_URL"])))
    db = real_db_manager
    user = User(id=1, email="owner@example.com", hashed_password="x", display_name="owner")
    db.add(user)
    book = Book(
        user_id=1,
        title="テスト作品",
        genre="ファンタジー",
        concept="テスト",
        synopsis="テストあらすじ",
        target_eps=1,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    book_id = book.id

    fake_zip = b"PK\x03\x04fake_zip_bytes"
    fake_engine = MagicMock()
    fake_engine.marketing.create_export_package = AsyncMock(
        return_value=(fake_zip, "export_1.zip")
    )

    from src.backend.routers import marketing as marketing_router

    original_get_engine = marketing_router.get_engine
    marketing_router.get_engine = MagicMock(return_value=fake_engine)

    try:
        from src.backend.server import app

        with TestClient(app) as tc:
            resp = tc.post(
                f"/api/marketing/export_package/{book_id}",
                json={"api_key": "test-key"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("application/zip")
            assert resp.content == fake_zip
    finally:
        marketing_router.get_engine = original_get_engine
        AppContainer.db.reset_override()
        os.environ.pop("AUTH_DISABLED", None)
