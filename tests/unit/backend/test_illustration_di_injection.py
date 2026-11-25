"""挿絵生成の DI 注入・保存経路の回帰テスト（PLAN_P1 TRACK-I / I2-I3）。

ADR 003 Increment 2: 生成結果が DB に保存される経路を修復する。

- G1: DI コンテナが IllustrationAgent に repo を注入しない
  → `_persist`（illustration_agent.py）が self.repo is None で保存をスキップしていた
- G2: DI コンテナが IllustrationWorkflow に repo を注入しない
  → Huey 経由の /batch が `assert self.repo is not None`（illustration_workflow.py:76）で落ちる
- G3: `repo.get_chapters(book_id)` が存在しない
  → assert 通過後も AttributeError になる
- G7: DataRepositoryFacade の Auto-mode フォールバック列挙に illustrations が無い
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GOOGLE_GENAI_API_KEY", "test-key-for-di")


@pytest.fixture()
def container():
    from src.core.container import AppContainer

    with patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "fake"}):
        yield AppContainer()


def test_agent_receives_repo_from_container(container) -> None:
    """G1 修復: DI 経由の IllustrationAgent に repo が注入される。"""
    agent = container.illustration_agent()
    assert agent.repo is not None, "DI コンテナが IllustrationAgent に repo を注入していない"


def test_workflow_receives_repo_from_container(container) -> None:
    """G2 修復: DI 経由の IllustrationWorkflow に repo が注入される（/batch の assert 対策）。"""
    workflow = container.illustration_workflow()
    assert workflow.repo is not None, "DI コンテナが IllustrationWorkflow に repo を注入していない"


def test_facade_auto_mode_resolves_illustration_repo() -> None:
    """G7 修復: UoW 未使用の Auto mode でも illustrations リポジトリ経由のメソッドが解決される。

    DataRepositoryFacade.__getattr__ のフォールバック列挙に illustrations が含まれていること。
    """
    import inspect

    from src.backend.database.repository import DataRepositoryFacade

    source = inspect.getsource(DataRepositoryFacade.__getattr__)
    # Auto-mode フォールバックの列挙（UoW モードの列挙とは別箇所）にも含まれること
    # UoW モード列挙（1 か所目）に加え、フォールバック列挙（2 か所目）にも出現する
    assert source.count('"illustrations"') >= 2, (
        "DataRepositoryFacade の Auto-mode フォールバック列挙に illustrations が含まれていない"
    )


class _FacadeLike:
    """DataRepositoryFacade 相当のスタブ。

    `get_chapters` は存在しない（= G3 の実環境 AttributeError を再現）。
    修復後の `get_all_non_anchor_chapters`（UoW 経由で async 解決）のみ提供する。
    """

    async def get_all_non_anchor_chapters(self, book_id: int, branch_id: int = 1, order_by: str = "ep_num"):
        return []


async def test_workflow_execute_survives_chapter_lookup() -> None:
    """G3 修復: chapters 取得が AttributeError にならず、execute が正常終了する。

    修正前は `repo.get_chapters` が存在せず AttributeError で落ちていた
    （facade は UoW 経由で解決するが ChapterRepository に get_chapters は存在しない）。
    """
    from src.agents.illustration_agent import IllustrationAgent
    from src.backend.workflows.illustration_workflow import IllustrationWorkflow
    from src.publishing.illustration.image_service import ImageService

    agent = IllustrationAgent(image_service=MagicMock(spec=ImageService))
    agent.repo = MagicMock()

    workflow = IllustrationWorkflow(illustration_agent=agent, repo=_FacadeLike())

    reporter = MagicMock()
    result = await workflow.execute(
        reporter,
        book_id=1,
        settings={"enableIllustration": True, "generateCover": False, "generateEpisodeIllustrations": True},
    )

    # chapters が空のため「表紙なし・話数 0 件」で正常終了する
    assert result["status"] == "success"
