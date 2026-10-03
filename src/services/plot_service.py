from typing import Any

from src.core.interfaces import IRepository


class PlotService:
    """プロット管理サービス"""

    def __init__(self, repo: IRepository):
        self.repo = repo

    async def get_plot(
        self, book_id: int, ep_num: int, branch_id: int | None = None
    ) -> Any | None:
        # branch_id は作品間で共有されるため、渡された場合は book_id も併せて絞る
        if branch_id is None:
            return await self.repo.get_plot(book_id, ep_num)
        return await self.repo.get_plot(branch_id, ep_num, branch_id=branch_id, book_id=book_id)

    async def get_plots_between(
        self, book_id: int, start_ep: int, end_ep: int, branch_id: int | None = None
    ) -> list[Any]:
        if branch_id is None:
            return await self.repo.get_plots_between(book_id, start_ep, end_ep)
        return await self.repo.get_plots_between(
            branch_id, start_ep, end_ep, book_id=book_id
        )

    async def update_plot_blueprint(
        self, branch_id: int, ep_num: int, blueprint: str, book_id: int | None = None
    ) -> None:
        await self.repo.update_plot_blueprint(branch_id, ep_num, blueprint, book_id=book_id)
