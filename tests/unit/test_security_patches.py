"""
Unit tests verifying Phase 2 security patches:
- Cypher query & column definition validation (SQL injection prevention)
- Admin endpoint authentication enforcement
"""

import pytest
from pydantic import ValidationError
from src.backend.routers.graph import CypherQueryRequest, router as graph_router
from src.backend.routers.system import router as system_router
from src.backend.auth import get_current_user, require_admin_user_or_key, require_api_key
from src.services.age_client import _sanitize_graph_name, _validate_column_def


def test_cypher_query_request_valid():
    """Valid column definition should be accepted."""
    req = CypherQueryRequest(query="MATCH (n) RETURN n", column_definition="(result agtype)")
    assert req.column_definition == "(result agtype)"

    req_multi = CypherQueryRequest(query="MATCH (n) RETURN n.id, n.name", column_definition="(id agtype, name agtype)")
    assert req_multi.column_definition == "(id agtype, name agtype)"


def test_cypher_query_request_sql_injection_rejection():
    """SQL injection attempts in column_definition must be rejected."""
    injections = [
        "(result agtype); DROP TABLE users; --",
        "(result agtype) -- comment",
        "(result agtype) /* comment */",
        "result agtype",  # missing parens
        "(res agtype) $$ SELECT 1",
    ]
    for inj in injections:
        with pytest.raises(ValidationError):
            CypherQueryRequest(query="MATCH (n) RETURN n", column_definition=inj)


def test_age_client_sanitization_helpers():
    """Deprecated stub sanitizers: 特殊文字は除去され、無効形式は False を返す。"""
    assert _sanitize_graph_name("knowledge_graph_1") == "knowledge_graph_1"
    # 非推奨スタブは ValueError の代わりに危険文字を除去する
    assert _sanitize_graph_name("graph; DROP TABLE books;") == "graphDROPTABLEbooks"
    assert _sanitize_graph_name("graph name with spaces") == "graphnamewithspaces"
    assert _sanitize_graph_name(None) is None

    # _validate_column_def は妥当性を bool で返す（単一 "col type" 形式のみ許容）
    assert _validate_column_def("res agtype") is True
    assert _validate_column_def("(res agtype); --") is False
    assert _validate_column_def(None) is False
    assert _validate_column_def("") is False


def test_graph_cypher_endpoint_requires_jwt():
    """The /api/graph/cypher endpoint must require a JWT (admin) user.

    書き込み系は JWT 必須 (API キーは読み取り専用)。旧実装は router レベルの
    JWT に加えて ``require_api_key`` も要求しており、同一の Authorization
    ヘッダーで両方を満たすリクエストが本番で作れない到達不能ルートだった。
    """
    route = next(r for r in graph_router.routes if getattr(r, "path", None) == "/api/graph/cypher")
    dep_calls = [d.dependency for d in route.dependencies]
    assert get_current_user in dep_calls, "get_current_user must be enforced on /api/graph/cypher"
    assert require_api_key not in dep_calls, (
        "require_api_key must not be combined with JWT on the same Authorization header "
        "(it makes the route unreachable in production)"
    )


def test_system_admin_endpoints_have_auth_dependencies():
    """All /admin/ endpoints in system router must require admin authentication.

    ハードニング（Phase 2）で全管理者ルートは ``require_admin_user_or_key`` に
    昇格した。このテストは「admin エンドポイントに何らかの認証依存性が必ず
    存在する」という安全 invariants を検証する。``require_api_key`` だけを
    要求するのではなく、管理者 JWT または API Key のいずれかを問じる
    require_admin_user_or_key を期待する（key 利用者は api_readonly に降格）。
    """
    admin_routes = [r for r in system_router.routes if "/admin/" in getattr(r, "path", "")]
    assert len(admin_routes) >= 6, f"Expected at least 6 admin routes, got {len(admin_routes)}"

    for r in admin_routes:
        dep_calls = [d.dependency for d in r.dependencies]
        assert require_admin_user_or_key in dep_calls, f"Route {r.path} missing require_admin_user_or_key dependency"
