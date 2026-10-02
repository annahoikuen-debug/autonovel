"""R1: シーン画像取得 API (`GET /images/{book_id}/{scene_name}`) のテスト。

フロントは「まだ生成されていない」を 404 ではなく 200 + ``found:false`` で
受け取る契約になっている。ここではその契約と、IDOR 防止 (所有権検証) を固定する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.backend.routers import illustrations as ill_router


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """UnitOfWork が要求する最小インターフェースだけを満たす。"""

    def __init__(self, rows):
        self._rows = rows
        self.added = []
        self.closed = False

    def in_transaction(self):
        return False

    async def begin_nested(self):
        return None

    async def execute(self, _stmt):
        return _FakeScalarResult(self._rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        self.closed = True


class _FakeUoW:
    def __init__(self, rows):
        self.session = _FakeSession(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _ill(ill_id: int, prompt: str, image_url: str):
    return SimpleNamespace(id=ill_id, prompt=prompt, image_url=image_url)


@pytest.fixture(autouse=True)
def _stub_ownership(monkeypatch):
    """所有権検証はここでは通し、判定ロジック自体に集中する。"""
    monkeypatch.setattr(
        ill_router,
        "verify_book_ownership",
        AsyncMock(return_value=SimpleNamespace(id=1)),
    )


def _patch_uow(monkeypatch, rows):
    """UnitOfWork 自体の生成を差し替える（session の lignes を注入）。"""
    uow = _FakeUoW(rows)
    monkeypatch.setattr(
        ill_router,
        "UnitOfWork",
        lambda *_a, **_k: uow,
    )
    return uow


@pytest.mark.asyncio
async def test_returns_found_true_with_matched_scene(monkeypatch):
    _patch_uow(monkeypatch, [_ill(3, "夕暮れの街で", "https://img/dusk.png")])

    result = await ill_router.get_scene_illustration(
        book_id=1,
        scene_name="夕暮れの街",
        current_user=SimpleNamespace(id=1, role="user"),
    )

    assert result == {
        "found": True,
        "image_url": "https://img/dusk.png",
        "illustration_id": 3,
    }


@pytest.mark.asyncio
async def test_no_illustration_returns_found_false_not_404(monkeypatch):
    _patch_uow(monkeypatch, [])

    result = await ill_router.get_scene_illustration(
        book_id=1,
        scene_name="存在しないシーン",
        current_user=SimpleNamespace(id=1, role="user"),
    )

    # 「未生成」はエラーではなく正常系。フロントが例外処理と区別できるようにする
    assert result == {"found": False, "image_url": None, "illustration_id": None}


@pytest.mark.asyncio
async def test_ignores_rows_with_empty_image_url(monkeypatch):
    """prompt 生成のみ（image_url 空）で永続化された行は「画像あり」と見なさない。"""
    _patch_uow(monkeypatch, [_ill(5, "夕暮れの街", "")])

    result = await ill_router.get_scene_illustration(
        book_id=1,
        scene_name="夕暮れの街",
        current_user=SimpleNamespace(id=1, role="user"),
    )

    assert result["found"] is False
    assert result["image_url"] is None


@pytest.mark.asyncio
async def test_falls_back_to_latest_when_scene_name_not_in_prompt(monkeypatch):
    """シーン名がプロンプトに無ければ最初に見つかった（=最新の）挿絵を返す。"""
    _patch_uow(
        monkeypatch,
        [
            _ill(9, "別のシーン", "https://img/other.png"),
            _ill(10, "また別のシーン", "https://img/newest.png"),
        ],
    )

    result = await ill_router.get_scene_illustration(
        book_id=1,
        scene_name="無関係な名前",
        current_user=SimpleNamespace(id=1, role="user"),
    )

    assert result["found"] is True
    # id 降順で返ってくるので先頭が「最新」
    assert result["illustration_id"] == 9


@pytest.mark.asyncio
async def test_verifies_book_ownership(monkeypatch):
    """他人の作品には挿絵を返さない（IDOR 防止）。"""
    verify = AsyncMock(return_value=SimpleNamespace(id=1))
    monkeypatch.setattr(ill_router, "verify_book_ownership", verify)
    _patch_uow(monkeypatch, [_ill(1, "x", "https://img/x.png")])

    await ill_router.get_scene_illustration(
        book_id=99,
        scene_name="シーン",
        current_user=SimpleNamespace(id=1, role="user"),
    )

    verify.assert_awaited_once()
    assert verify.await_args.args[0] == 99
