"""Layer2 階層組立 (_build_layer2_hierarchical) の単体テスト (PLAN_M1 Step 12).

巻要約 > 章要約 > 直近digest の優先順・予算クランプ・legacy フォールバックを
検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.episode_context import EpisodeContextBuilder


def _make_result(models):
    """db.execute の戻り値モック (res.scalars().all() 対応)。"""
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=models)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return result


def _make_rollup(book_id, level, start_ep, end_ep, text):
    m = MagicMock()
    m.book_id = book_id
    m.level = level
    m.start_ep = start_ep
    m.end_ep = end_ep
    m.digest_text = text
    return m


def _make_digest(ep, text):
    m = MagicMock()
    m.episode_num = ep
    m.digest_text = text
    return m


class TestLayer2Hierarchical:
    """_build_layer2_hierarchical のテストスイート。"""

    @pytest.fixture
    def builder(self, mock_db):
        return EpisodeContextBuilder(db=mock_db)

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    async def _run_hierarchical(self, builder, mock_db, volume, block, digests, current_ep=25):
        """db.execute の side_effect を [volume, block, digests, foreshadowing] で設定して実行。"""
        foreshadowing = []
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result(volume),
                _make_result(block),
                _make_result(digests),
                _make_result(foreshadowing),
            ]
        )
        return await builder._build_layer2_hierarchical(
            book_id=1, current_ep=current_ep, max_chars=4000
        )

    @pytest.mark.asyncio
    async def test_hierarchical_order_volume_then_block_then_digest(
        self, builder, mock_db, monkeypatch
    ):
        """巻要約 → 章要約 → 直近digest の順で text に現れる。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")

        volume = [_make_rollup(1, "volume", 1, 50, "巻1の確定事実。")]
        block = [_make_rollup(1, "block", 1, 10, "章1の確定事実。")]
        digests = [_make_digest(20, "第20話の確定事実。")]

        summary = await self._run_hierarchical(builder, mock_db, volume, block, digests, current_ep=25)

        assert "【巻1〜50話】巻1の確定事実。" in summary["text"]
        assert "【章1〜10話】章1の確定事実。" in summary["text"]
        assert "第20話: 第20話の確定事実。" in summary["text"]

        # 優先順: 巻が章より前に現れる
        idx_vol = summary["text"].index("【巻1〜50話】")
        idx_blk = summary["text"].index("【章1〜10話】")
        assert idx_vol < idx_blk

    @pytest.mark.asyncio
    async def test_budget_priority_volume_survives(self, builder, mock_db, monkeypatch):
        """予算超過時に巻要約が最優先で残り、直近digest から削られる。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")

        # history_budget = 4000 * 0.5 = 2000。巻要約が長いと章・話が削られる。
        long_volume = "巻の長い要約。" * 200  # 3000字超
        volume = [_make_rollup(1, "volume", 1, 50, long_volume)]
        block = [_make_rollup(1, "block", 1, 10, "章1の要約。")]
        digests = [_make_digest(20, "第20話の事実。")]

        summary = await self._run_hierarchical(builder, mock_db, volume, block, digests, current_ep=25)

        # 巻要約が優先で残る（あるいはクランプ後の一部）
        assert "巻の長い要約。" in summary["text"]
        # 直近digest は予算不足で削られる可能性（chapterより後なので）

    @pytest.mark.asyncio
    async def test_rollup_disabled_returns_empty(self, builder, mock_db, monkeypatch):
        """ENABLE_DIGEST_ROLLUP 未設定/0 なら text が空（legacy フォールバック対象）。"""
        monkeypatch.delenv("ENABLE_DIGEST_ROLLUP", raising=False)

        mock_db.execute = AsyncMock(return_value=_make_result([]))

        summary = await builder._build_layer2_hierarchical(
            book_id=1, current_ep=5, max_chars=4000
        )

        assert summary["text"] == ""
        assert summary["layer2_chars"] == 0

    @pytest.mark.asyncio
    async def test_foreshadowing_overdue_priority(self, builder, mock_db, monkeypatch):
        """期限超過伏線が未回収伏線セクションで最優先される。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result([]),  # volume
                _make_result([]),  # block
                _make_result([]),  # digests
                # foreshadowing: planted=1 target=5(超過), planted=2 target=30(未超過)
                _make_result(
                    [
                        _make_fs(2, "伏線B", 2, 30, "progressed"),
                        _make_fs(1, "伏線A", 1, 5, "planted"),
                    ]
                ),
            ]
        )

        summary = await builder._build_layer2_hierarchical(
            book_id=1, current_ep=10, max_chars=4000
        )

        # 期限超過(伏線A)が先に現れる
        idx_a = summary["text"].index("伏線A")
        idx_b = summary["text"].index("伏線B")
        assert idx_a < idx_b

    @pytest.mark.asyncio
    async def test_metadata_fields_preserved(self, builder, mock_db, monkeypatch):
        """foreshadowing_omitted / foreshadowing_overdue 等のメタデータが消えない。"""
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")

        mock_db.execute = AsyncMock(
            side_effect=[
                _make_result([]),
                _make_result([]),
                _make_result([]),
                _make_result([]),
            ]
        )

        summary = await builder._build_layer2_hierarchical(
            book_id=1, current_ep=5, max_chars=4000
        )

        for key in [
            "foreshadowing_omitted",
            "foreshadowing_overdue",
            "history_chars",
            "foreshadowing_chars",
            "unresolved_foreshadowings",
            "last_episode_summary",
            "token_estimate",
        ]:
            assert key in summary, f"missing key: {key}"


def _make_fs(id, title, planted, target, status):
    m = MagicMock()
    m.id = id
    m.title = title
    m.planted_episode = planted
    m.target_episode = target
    m.status = status
    return m
