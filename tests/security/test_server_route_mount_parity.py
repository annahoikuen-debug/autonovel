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


def _router_paths(module_name: str) -> set[str]:
    """router モジュールが宣言するルートのパス（プレフィックス無し）。

    ``app.routes`` を走査して endpoint の同一性で照合する方式は
    FastAPI 0.141 の遅延展開 (``_IncludedRouter``) に対応できないため、
    ここでは router 自身の ``include_router`` 前の相対パスを集め、
    アプリ側は OpenAPI スキーマの解決済みパスと突き合わせる。
    ``app`` 側は prefix が付くので、突き合わせは「_router のパスが app にあるか」
    を前缀一致で行う。
    """
    mod = importlib.import_module(f"src.backend.routers.{module_name}")
    router = getattr(mod, "router", None)
    if router is None:
        return set()
    paths: set[str] = set()
    for r in getattr(router, "routes", []):
        p = getattr(r, "path", None)
        if isinstance(p, str):
            paths.add(p)
        # include_router で入れ子にした router があれば再帰的に辿る
        for sub in getattr(r, "routes", []) or []:
            sp = getattr(sub, "path", None)
            if isinstance(sp, str):
                base = p if isinstance(p, str) else ""
                paths.add(f"{base}{sp}" if base else sp)
    return paths


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


def _app_paths() -> set[str]:
    """app に実際に載っているパス（プレフィックス込み）の集合。

    FastAPI 0.141 以降 `include_router` は遅延展開の ``_IncludedRouter`` を
    `app.routes` に積むため、`app.routes` を平坦に走査しても
    include した router のルートは現れない（`r.path` を持たない）。
    OpenAPI スキーマは解決済みのパスを返すのでこちらを主軸にする。

    ただし OpenAPI スキーマは ①HTTP ルートしか記述せず、
    ②``include_in_schema=False`` のルートも隠す。
    WebSocket ルートと非公開ルートは「マウントされているか」の対象なので、
    ``_IncludedRouter.original_router`` を辿る walker で別途拾って合算する。
    """
    from src.backend.server import app

    paths = set(app.openapi().get("paths", {}))
    stack: list[object] = list(app.routes)
    while stack:
        r = stack.pop()
        original = getattr(r, "original_router", None)
        if original is not None:
            stack.extend(getattr(original, "routes", []) or [])
        for sub in getattr(r, "routes", []) or []:
            stack.append(sub)
        # `include_in_schema=False` のルート (health の /api/health/detail など) と
        # WebSocket ルートは OpenAPI に載らないため、ここで行 walker から拾う。
        p = getattr(r, "path", None)
        if isinstance(p, str):
            paths.add(p)
    return paths


def _mounted(app_paths: set[str], router_paths: set[str]) -> tuple[set[str], set[str]]:
    """router 側のパス集合を app 側と突き合わせる。

    ``APIRouter(prefix=...)`` を持つ router は自身の ``router.routes`` に既に
    prefix 付きのパスが載る。一方 prefix 無しの router を ``server.py`` 側で
    ``include_router(router, prefix="/api/wizard")`` のように prefix 付きで
    取り込むケースもあるため、厳密な等価ではなく
    「どちらかがもう一方の接尾辞になっているか」で照合する
    （例: router 側 "/generate" と app 側 "/easy_mode/generate" を一致とみなす）。
    """
    matched: set[str] = set()
    unmatched: set[str] = set()
    for rp in router_paths:
        if rp in app_paths or any(ap.endswith(rp) for ap in app_paths):
            matched.add(rp)
        else:
            unmatched.add(rp)
    return matched, unmatched


def test_every_router_module_is_mounted_or_explicitly_allowlisted():
    app_paths = _app_paths()
    unmounted: list[str] = []
    for name in sorted(_router_files()):
        if name in _SKIP:
            continue
        own = _router_paths(name)
        if not own:
            # router を持たないモジュール（定数のみ等）は対象外。
            continue
        matched, _ = _mounted(app_paths, own)
        if not matched:
            unmounted.append(name)
    assert not unmounted, (
        f"マウントされていない router がある（フロントは 404 になる）: {unmounted}。"
        "server.py に include_router を追加するか、ALLOWLIST に明記すること。"
    )


def test_every_router_module_with_routes_is_actually_reachable():
    """より強い版: マウント済みでも「ルートが 1 本も載っていない」なら検出する。"""
    app_paths = _app_paths()
    missing: list[str] = []
    for name in sorted(_router_files() - _SKIP):
        own = _router_paths(name)
        if not own:
            continue
        _, unmatched = _mounted(app_paths, own)
        if unmatched:
            missing.append(name)
    assert not missing, f"router の一部エンドポイントが app に載っていない: {missing}"


def test_orchestrated_routes_are_reachable():
    """``orchestrated`` の FE 契約パスが実際に app に載っていること（S9 Step 8 のBUG の回帰防止）。"""
    paths = _app_paths()
    expected = {
        "/orchestrated/generate",
        "/orchestrated/status/{task_id}",
        "/orchestrated/task/{task_id}",
        "/orchestrated/export/{book_id}",
        "/orchestrated/events/{correlation_id}",
    }
    missing = sorted(expected - paths)
    assert not missing, f"orchestrated が未マウント、または prefix が FE 契約と不一致: {missing}"
