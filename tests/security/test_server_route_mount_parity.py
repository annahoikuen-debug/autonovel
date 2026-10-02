"""``src/backend/routers/*.py`` のうち ``server.py`` でマウントされていないものを検出する。

``orchestrated.py`` は frontend から実際に呼ばれていたがマウントされておらず、
常に 404 になっていた。本テストはその種類の不一致を恒久的に検出する。

PLAN_H1R H1R-3 で判定方式を変更した:
旧実装は ``server.py`` のソース文字列を grep して
``include_router(<name>.router)`` を列挙していた（``re.findall``）。
これは **「include_router が書かれた」ことしか述べておらず**、
実際にアプリへ載るWhetherかを検査していない。実際 H1R-3 で
``health`` を ``health as health_router`` にエイリアスしただけで
誤検出（未マウント扱い）が起きていた。

現在は **router が持つ endpoint 関数が app に登録されているか**を
オブジェクト同一性で判定する。prefix の有無に依存せず、エイリアスにも強い。
（``docs/TEST_STRATEGY.md``「ソース文字列 grep を assert にするな」の適用）
"""
from __future__ import annotations

import glob
import importlib
import os

# 同一 basename が 2 つ以上 ROUTERS ディレクトリに存在しない前提
ROUTER_DIR = "src/backend/routers"


def _router_files() -> set[str]:
    return {
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ROUTER_DIR, "*.py"))
        if not os.path.basename(p).startswith("__")
    }


def _app_endpoints() -> set[int]:
    """app に登録済みルートの endpoint 関数の id 集合。"""
    from src.backend.server import app

    return {id(r.endpoint) for r in app.routes if callable(getattr(r, "endpoint", None))}


def _router_endpoints(module_name: str) -> set[int]:
    mod = importlib.import_module(f"src.backend.routers.{module_name}")
    router = getattr(mod, "router", None)
    if router is None:
        return set()
    return {id(r.endpoint) for r in getattr(router, "routes", []) if callable(
        getattr(r, "endpoint", None)
    )}


# metrics は server.py の独立 /metrics エンドポイントと役割が重複するため
# 「意図的にマウントしない」ことが文書化されている。
ALLOWLIST = {"metrics"}

# plugin_registry によって条件付きマウントされる router。
# プラグインを無効にした環境（testing プロファイルなど）では app に現れない。
# 理由 必须（同じ内容が tests/regression/test_H1_routing_drift.py にある）。
CONDITIONAL_MOUNTS = {
    "multimedia": (
        "server.py:194 `if plugin_registry.is_enabled(\"multimedia\")` が true のときだけ "
        "prefix=\"/multimedia\" でマウントされる。testing プロファイルではプラグインが無効。"
        "TODO(H1-10): プラグイン有効時の検証を統合テストに追加"
    ),
}

_SKIP = ALLOWLIST | set(CONDITIONAL_MOUNTS)


def test_conditional_mounts_have_a_reason():
    """条件付きマウントを allowlist に挙げたなら、理由と TODO 番号を書く（§9）。"""
    for name, reason in CONDITIONAL_MOUNTS.items():
        assert reason.strip(), f"{name} の CONDITIONAL_MOUNTS に理由が無い"
        assert "TODO(H1-" in reason, (
            f"{name} の CONDITIONAL_MOUNTS に TODO(H1-N) の番号が無い（§9: 数値外れ禁止）"
        )


def test_every_router_module_is_mounted_or_explicitly_allowlisted():
    app_endpoints = _app_endpoints()
    unmounted: list[str] = []
    for name in sorted(_router_files()):
        if name in _SKIP:
            continue
        own = _router_endpoints(name)
        if not own:
            # router を持たないモジュール（定数のみ等）は対象外。
            continue
        if not (own & app_endpoints):
            unmounted.append(name)
    assert not unmounted, (
        f"マウントされていない router がある（フロントは 404 になる）: {unmounted}。"
        "server.py に include_router を追加するか、ALLOWLIST に明記すること。"
    )


def test_every_router_module_with_routes_is_actually_reachable():
    """より強い版: マウント済みでも「ルートが 1 本も載っていない」なら検出する。"""
    app_endpoints = _app_endpoints()
    missing: list[str] = []
    for name in sorted(_router_files() - _SKIP):
        own = _router_endpoints(name)
        if not own:
            continue
        if own - app_endpoints:
            missing.append(name)
    assert not missing, f"router の一部エンドポイントが app に載っていない: {missing}"


def test_orchestrated_routes_are_reachable():
    """``orchestrated`` の FE 契約パスが実際に app に載っていること（S9 Step 8 のBUG の回帰防止）。"""
    from src.backend.server import app

    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    expected = {
        "/orchestrated/generate",
        "/orchestrated/status/{task_id}",
        "/orchestrated/task/{task_id}",
        "/orchestrated/export/{book_id}",
        "/orchestrated/events/{correlation_id}",
    }
    missing = sorted(expected - paths)
    assert not missing, f"orchestrated が未マウント、または prefix が FE 契約と不一致: {missing}"
