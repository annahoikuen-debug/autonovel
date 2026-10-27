"""branches.py の cross-tenant 脆弱性の反証テスト。

GET/POST/DELETE /api/branches/{book_id}/nodes... は ``requires_book_ownership`` で
``book_id`` の所有者は検証していたが、ハンドラが操作する ``branch_id`` が
その book に属するかどうかは検証していなかった (``src/backend/routers/branches.py:702,721,745``)。

このテストは「他人の book_id + 他人の branch_id」の組み合わせが
``load_branch_graph`` に到達しないことを保証する。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.backend.routers.branches import list_branch_nodes, create_branch_node, delete_branch_node


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeSession:
    """``uow.session.scalar(select(...))`` だけを模した最小セッション。"""

    def __init__(self, owner_book_id: int | None):
        self.owner_book_id = owner_book_id
        self.executed: list = []

    async def scalar(self, stmt):
        self.executed.append(stmt)
        return self.owner_book_id


class _FakeUow:
    def __init__(self, owner_book_id: int | None):
        self.session = _FakeSession(owner_book_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_name",
    ["list_branch_nodes", "create_branch_node", "delete_branch_node"],
)
async def test_branch_node_endpoints_reject_foreign_branch(endpoint_name):
    """他人のブランチ ID を渡すと 403 になり、リポジトリに到達しないこと。"""
    owner_book_id = None  # 「この branch_id は book_id に属さない」を模す
    uow = _FakeUow(owner_book_id)
    endpoint = {
        "list_branch_nodes": list_branch_nodes,
        "create_branch_node": create_branch_node,
        "delete_branch_node": delete_branch_node,
    }[endpoint_name]

    with pytest.raises(HTTPException) as exc:
        if endpoint_name == "list_branch_nodes":
            await endpoint(book_id=999, branch_id=4242, session=uow.session)
        elif endpoint_name == "create_branch_node":
            await endpoint(book_id=999, branch_id=4242, node={"id": "n1"}, session=uow.session)
        else:
            await endpoint(book_id=999, branch_id=4242, node_id="n1", session=uow.session)

    assert exc.value.status_code == 403, (
        f"{endpoint_name} は foreign branch を 403 で拒否すべき。"
        f"実際: {exc.value.status_code}"
    )
