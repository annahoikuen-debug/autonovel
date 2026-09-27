"""
UI/UX と実機能の接続検証スクリプト。

フロントエンドが実際に叩く API エンドポイントが、
バックエンドに定義されているかを照合する。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# scripts/verify_ui_api_linkage.py -> autonovel/
ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
# routers/ 配下と、include_router を書く server.py などのアプリルートをまとめて走査する
BACKEND_ROUTERS = ROOT / "src" / "backend" / "routers"
BACKEND_APP_FILES = sorted(
    set(BACKEND_ROUTERS.rglob("*.py"))
    | set((ROOT / "src" / "backend").glob("*.py"))
)

# ---------------------------------------------------------------- フロントの API 呼び出し収集
DIRECT_RE = re.compile(
    r"""(?:apiFetch|fetch)\s*(?:<[^>]*>)?\s*\(\s*[`"']([^`"']+)[`"']"""
)
BASE_RE = re.compile(
    r"""(?:const|let)\s+(\w*(?:BASE|base)\w*)\s*[:=]\s*["']([^"']+)["']"""
)
COMPOSED_RE = re.compile(r"`\$\{(\w+)\}([^`]*)`")
TEMPLATE_ANY_RE = re.compile(r"\$\{[^}]*\}")


def collect_frontend_calls() -> set[str]:
    """フロントの API 呼び出しパス（動的部分を {} に置換して静的評価）を集める"""
    raw: set[str] = set()

    for f in FRONTEND_SRC.rglob("*.ts*"):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # ベースパス定数は「そのファイル内だけ」で有効（モジュールスコープ）。
        # グローバルに収集すると別ファイルの同名定数を誤って引き当ててしまう。
        bases: dict[str, str] = {
            m.group(1): m.group(2) for m in BASE_RE.finditer(text)
        }

        # (1) apiFetch(`...`) / fetch("...") の直接呼び出し
        for m in DIRECT_RE.finditer(text):
            raw.add(m.group(1))

        # (2) `${BASE_URL}/path` 形式の合成
        for m in COMPOSED_RE.finditer(text):
            var, tail = m.group(1), m.group(2)
            base = bases.get(var)
            if base is not None:
                raw.add(base.rstrip("/") + tail)

    result: set[str] = set()
    for p in raw:
        # 動的パラメータを {} に
        q = TEMPLATE_ANY_RE.sub("{}", p)
        # クエリとハッシュを除去
        q = q.split("?")[0].split("#")[0]
        # 余分なスラッシュを畳む
        q = re.sub(r"/{2,}", "/", q)
        if len(q) > 1 and q.endswith("/"):
            q = q[:-1]
        if q.startswith("/") and len(q) > 1:
            result.add(q)
    return result


# ---------------------------------------------------------------- バックエンドのルート収集
# デコレータの引数は複数行にまたがることがあるので、DOTALL で寛容に拾う
ROUTE_RE = re.compile(
    r"""@router\.(?:get|post|put|patch|delete)\s*\((?:\s|#[^\n]*\n)*?["']([^"']+)["']""",
    re.DOTALL,
)
PREFIX_RE = re.compile(r"""APIRouter\s*\(\s*prefix\s*=\s*["']([^"']+)["']""")
INCLUDE_PREFIX_RE = re.compile(
    r"""include_router\s*\(\s*\w+\s*,\s*prefix\s*=\s*["']([^"']+)["']"""
)
# include_router(plots.router, prefix="/api/plots") のような形を拾う
INCLUDE_FULL_RE = re.compile(
    r"""include_router\s*\(\s*(\w+)(?:\.router)?\s*,\s*prefix\s*=\s*["']([^"']+)["']""",
    re.DOTALL,
)
WS_RE = re.compile(r"""@router\.websocket\s*\(\s*["']([^"']+)["']""")


def collect_backend_routes() -> set[str]:
    """各 router モジュールの「パス」と prefix を集める"""
    router_prefix: dict[str, str] = {}
    router_paths: dict[str, list[str]] = {}

    for f in BACKEND_ROUTERS.rglob("*.py"):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pm = PREFIX_RE.search(text)
        router_prefix[f.stem] = pm.group(1) if pm else ""
        paths = [m.group(1) for m in ROUTE_RE.finditer(text)]
        paths += [m.group(1) for m in WS_RE.finditer(text)]
        router_paths[f.stem] = paths

    # include_router(module, prefix="...") で足される prefix を収集
    # （server.py などに書いたものが実際に生效する）
    include_prefix: dict[str, str] = {}
    for f in BACKEND_APP_FILES:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in INCLUDE_FULL_RE.finditer(text):
            mod = m.group(1)
            if mod in router_prefix:
                # include_router の prefix 指定は APIRouter の prefix を上書きする
                include_prefix[mod] = m.group(2)

    routes: set[str] = set()

    def norm(p: str) -> str:
        n = re.sub(r"/{2,}", "/", p)
        if len(n) > 1 and n.endswith("/"):
            n = n[:-1]
        return n or "/"

    for stem, paths in router_paths.items():
        own = router_prefix.get(stem, "")
        applied = include_prefix.get(stem)
        # include_router の prefix 指定が優先（これが実際に公開されるパス）
        base = applied if applied is not None else own
        for p in paths:
            routes.add(norm(base.rstrip("/") + p))
        # prefix なし（素通し）で mount されるケース
        if applied is None and not own:
            for p in paths:
                routes.add(norm(p))
    return routes


# ---------------------------------------------------------------- 照合
def to_pattern(path: str) -> re.Pattern[str]:
    """動的パラメータ（{} や {book_id}）をワイルドカードにした正規表現を作る"""
    segs = re.split(r"(\{[^}]*\})", path)
    body = "".join(
        r"[^/]+" if s.startswith("{") else re.escape(s) for s in segs
    )
    return re.compile("^" + body + "$")


def match(route: str, patterns: list[re.Pattern[str]]) -> str | None:
    if route in patterns and False:  # 文字列一致は下方で扱う
        return route
    for p in patterns:
        if p.match(route):
            return p.pattern
    return None


KEY_KEYWORDS = (
    "/api/plots",
    "/api/stream",
    "/api/cost",
    "/api/editor",
    "/api/books",
    "/api/graph",
    "/api/branches",
    "/api/export",
    "/api/novel",
    "/api/commercial",
    "/api/collab",
    "/api/illustrations",
    "/api/issues",
    "/multimedia",
    "/api/ai",
    "/api/publishing-assistant",
)


def main() -> int:
    front = collect_frontend_calls()
    back = collect_backend_routes()
    back_patterns = [(to_pattern(b), b) for b in sorted(back)]

    def hit(path: str) -> str | None:
        for p, orig in back_patterns:
            if p.match(path):
                return orig
        return None

    key_paths = sorted(p for p in front if any(k in p for k in KEY_KEYWORDS))

    print("=" * 78)
    print("UI/UX と実機能の接続検証")
    print("=" * 78)
    print(f"フロントの API 呼び出し: {len(front)} パス")
    print(f"バックエンドのルート定義: {len(back)} ルート")
    print()

    print("-" * 78)
    print("[1] 主要導線")
    print("-" * 78)
    ok = 0
    ng: list[str] = []
    for p in key_paths:
        h = hit(p)
        if h:
            ok += 1
            print(f"  OK   {p}")
            print(f"       -> {h}")
        else:
            ng.append(p)
            print(f"  NG   {p}")
            print(f"       -> バックエンドに定義が見つからない")
    print()

    unmatched = [p for p in sorted(front) if not hit(p)]
    print("-" * 78)
    print(f"[2] 未マッチ（要確認）: {len(unmatched)} 件")
    print("-" * 78)
    for p in unmatched:
        print(f"  - {p}")
    print()

    print("=" * 78)
    print(f"結論: 主要導線 {ok}/{len(key_paths)} 接続済み / 全体 {len(front)-len(unmatched)}/{len(front)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
