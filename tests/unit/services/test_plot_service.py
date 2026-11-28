"""src/services/plot_service.py (PlotService) の単体テスト."""

from __future__ import annotations

from typing import Any

import pytest

from src.services.plot_service import PlotService


class _StubRepository:
    """PlotService に渡すスタブリポジトリ（モックではなく単純実装）。"""

    def __init__(self):
        self.get_plot_calls: list[tuple] = []
        self.get_plots_between_calls: list[tuple] = []
        self.update_plot_blueprint_calls: list[tuple] = []
        self.plot_return_value = None
        self.plots_return_value: list[Any] = []

    async def get_plot(self, *args, **kwargs):
        self.get_plot_calls.append((args, kwargs))
        return self.plot_return_value

    async def get_plots_between(self, *args, **kwargs):
        self.get_plots_between_calls.append((args, kwargs))
        return list(self.plots_return_value)

    async def update_plot_blueprint(self, *args, **kwargs):
        self.update_plot_blueprint_calls.append((args, kwargs))


class TestPlotService:
    """PlotService のテスト."""

    @pytest.mark.asyncio
    async def test_get_plot_without_branch_id(self):
        repo = _StubRepository()
        repo.plot_return_value = {"id": 1, "title": "プロット"}
        service = PlotService(repo)

        result = await service.get_plot(book_id=42, ep_num=3)

        assert result == {"id": 1, "title": "プロット"}
        assert len(repo.get_plot_calls) == 1
        args, kwargs = repo.get_plot_calls[0]
        assert args == (42, 3)
        assert kwargs == {}

    @pytest.mark.asyncio
    async def test_get_plot_with_branch_id(self):
        repo = _StubRepository()
        repo.plot_return_value = {"id": 2, "title": "ブランチプロット"}
        service = PlotService(repo)

        result = await service.get_plot(book_id=42, ep_num=3, branch_id=99)

        assert result == {"id": 2, "title": "ブランチプロット"}
        assert len(repo.get_plot_calls) == 1
        args, kwargs = repo.get_plot_calls[0]
        assert args == (99, 3)
        assert kwargs == {"branch_id": 99, "book_id": 42}

    @pytest.mark.asyncio
    async def test_get_plots_between_without_branch_id(self):
        repo = _StubRepository()
        repo.plots_return_value = [{"ep": 1}, {"ep": 2}, {"ep": 3}]
        service = PlotService(repo)

        result = await service.get_plots_between(book_id=42, start_ep=1, end_ep=3)

        assert len(result) == 3
        assert len(repo.get_plots_between_calls) == 1
        args, kwargs = repo.get_plots_between_calls[0]
        assert args == (42, 1, 3)
        assert kwargs == {}

    @pytest.mark.asyncio
    async def test_get_plots_between_with_branch_id(self):
        repo = _StubRepository()
        repo.plots_return_value = [{"ep": 1}]
        service = PlotService(repo)

        result = await service.get_plots_between(book_id=42, start_ep=1, end_ep=3, branch_id=99)

        assert len(result) == 1
        args, kwargs = repo.get_plots_between_calls[0]
        assert args == (99, 1, 3)
        assert kwargs == {"book_id": 42}

    @pytest.mark.asyncio
    async def test_update_plot_blueprint_without_book_id(self):
        repo = _StubRepository()
        service = PlotService(repo)

        await service.update_plot_blueprint(branch_id=99, ep_num=3, blueprint="blueprint text")

        assert len(repo.update_plot_blueprint_calls) == 1
        args, kwargs = repo.update_plot_blueprint_calls[0]
        assert args == (99, 3, "blueprint text")
        assert kwargs == {"book_id": None}

    @pytest.mark.asyncio
    async def test_update_plot_blueprint_with_book_id(self):
        repo = _StubRepository()
        service = PlotService(repo)

        await service.update_plot_blueprint(branch_id=99, ep_num=3, blueprint="blueprint text", book_id=42)

        args, kwargs = repo.update_plot_blueprint_calls[0]
        assert args == (99, 3, "blueprint text")
        assert kwargs == {"book_id": 42}
