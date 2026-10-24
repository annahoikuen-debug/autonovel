"""書き込み系エンドポイントの認証ポリシー検証。

背景（レビューで検出した缺陷）:

* 一部の書き込みエンドポイントは ``require_api_key`` のみ、別のものは
  router レベルの ``get_current_user`` + 個別の ``require_api_key`` を要求していた。
  両者は **同じ Authorization ヘッダー** を見るため、本番
  (``AUTH_DISABLED=False``) では JWT か API キーのどちらかしか送れず、
  両方を通過するリクエストが原理的に存在しない = 到達不能ルートになっていた。
* API キー単独の書き込みは所有者を ``_get_dev_mock_user()`` (user id=1) に
  丸めていたため、共有 API キー 1 本で全ユーザーを装える権限昇格だった。

方針: 書き込みは JWT 必須 (API キーは読み取り専用)。
サーバー間連携向け commercial 系のみ ``ALLOW_API_KEY_WRITES`` で
API キーをオプトインで受け付ける（書き込み主体はサービスアカウント）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.backend import auth as auth_mod
from src.backend.auth import (
    get_current_user_or_service_key,
    require_admin_user,
    require_api_key,
)
from src.backend.config import settings
from src.backend.routers import commercial, easy_mode, graph, novel, publishing_assistant, streaming
from src.backend.routers import tasks as tasks_router
from src.backend.database.models import User

_JWT_DEP_NAMES = {"get_current_user", "get_current_user_or_service_key", "require_admin_user"}


def _iter_routes(module):
    router = module.router
    for route in router.routes:
        path = getattr(route, "path", None)
        if path is not None:
            yield path, route


def _route_deps(route) -> list:
    return [d.dependency for d in getattr(route, "dependencies", [])]


def _all_dep_names(route) -> set[str]:
    """ルート + ハンドラの依存を再帰的に名前で集める。"""
    names: set[str] = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            dep = getattr(sub, "call", None) or getattr(sub, "dependency", None)
            if dep is not None:
                names.add(getattr(dep, "__name__", str(dep)))
            walk(sub)

    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        walk(dependant)
    return names


@pytest.mark.parametrize(
    "module",
    [commercial, easy_mode, graph, novel, publishing_assistant, streaming, tasks_router],
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_no_route_double_authenticates_the_same_header(module):
    """どのルートも JWT 依存と API キー依存を同時に要求しない。

    同一の Authorization ヘッダーを両方満たす必要があるルートは、
    本番では到達不能になる（片方しか送れない）。
    """
    offenders = []
    for path, route in _iter_routes(module):
        names = _all_dep_names(route)
        if "require_api_key" in names and any(n in names for n in _JWT_DEP_NAMES):
            offenders.append(path)
    assert not offenders, f"{module.__name__}: JWT と API キーを同時に要求するルートが残っています: {offenders}"


def test_write_endpoints_do_not_accept_api_key():
    """POST/PUT/DELETE は ``require_api_key`` を依存に含めない。"""
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = []
    for module in (commercial, easy_mode, graph, novel, publishing_assistant, streaming, tasks_router):
        for path, route in _iter_routes(module):
            methods = {m for m in getattr(route, "methods", set()) if m not in ("HEAD", "OPTIONS")}
            if not (methods & write_methods):
                continue
            if "require_api_key" in _all_dep_names(route):
                offenders.append(f"{module.__name__}{path}")
    assert not offenders, f"書き込み系に API キー依存が残っています: {offenders}"


def test_easy_mode_generate_requires_task_owner_dependency():
    """``POST /easy_mode/generate`` は所有者を特定できる JWT 依存を持つ。"""
    route = next(r for p, r in _iter_routes(easy_mode) if p == "/generate" and "POST" in r.methods)
    names = _all_dep_names(route)
    assert "get_easy_mode_user" in names
    assert "require_api_key" not in names


def test_admin_recover_requires_admin_user():
    """``POST /api/tasks/admin/recover`` は admin JWT のみを要求する。"""
    route = next(r for p, r in _iter_routes(tasks_router) if p.endswith("/admin/recover"))
    assert require_admin_user in _route_deps(route)
    assert require_api_key not in _route_deps(route)


def test_graph_cypher_requires_admin_jwt():
    route = next(r for p, r in _iter_routes(graph) if p == "/api/graph/cypher")
    names = _all_dep_names(route)
    assert "get_current_user" in names
    assert "require_api_key" not in names


def _user(id_: int = 7, email: str = "svc@example.com", status: str = "active") -> User:
    return User(id=id_, email=email, status=status, role="user", display_name="svc")


def _db_returning(user):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result
    return db


async def test_service_key_denied_by_default(monkeypatch):
    """既定 (ALLOW_API_KEY_WRITES=False) では API キーによる書き込みは 401。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(settings, "ALLOW_API_KEY_WRITES", False)
    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: k)

    with pytest.raises(HTTPException) as exc:
        await get_current_user_or_service_key(token=None, authorization="k1", db=_db_returning(None))
    assert exc.value.status_code == 401


async def test_service_key_resolves_service_account_when_opted_in(monkeypatch):
    """ALLOW_API_KEY_WRITES=True ではサービスアカウントを書き込み主体として返す。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(settings, "ALLOW_API_KEY_WRITES", True)
    monkeypatch.setattr(settings, "API_KEY_SERVICE_EMAIL", "svc@example.com")
    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: k)

    svc = _user()
    user = await get_current_user_or_service_key(token=None, authorization="k1", db=_db_returning(svc))
    assert user.email == "svc@example.com"
    assert user.id == 7


async def test_service_key_rejects_when_service_account_missing(monkeypatch):
    """サービスアカウント未登録なら、なりすましを防ぐため 403。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    monkeypatch.setattr(settings, "ALLOW_API_KEY_WRITES", True)
    monkeypatch.setattr(settings, "API_KEY_SERVICE_EMAIL", "missing@example.com")
    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: k)

    with pytest.raises(HTTPException) as exc:
        await get_current_user_or_service_key(token=None, authorization="k1", db=_db_returning(None))
    assert exc.value.status_code == 403


async def test_service_key_prefers_jwt(monkeypatch):
    """JWT が在れば API キーを経由せず JWT のユーザーを返す。"""
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)
    jwt_user = _user(id_=3, email="jwt@example.com")
    monkeypatch.setattr(auth_mod, "get_current_user", AsyncMock(return_value=jwt_user))

    user = await get_current_user_or_service_key(token="jwt-token", authorization="", db=_db_returning(None))
    assert user.email == "jwt@example.com"


def test_policy_is_documented_in_auth_module():
    """認証方針 (APIキーは読み取り専用) が auth モジュールで明文化されている。"""
    doc = auth_mod.__doc__ or ""
    assert "読み取り専用" in doc
