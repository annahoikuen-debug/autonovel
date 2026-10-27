"""locustfile の静的チェック。

``import locust`` は ssl を monkey-patch するため pytest プロセス内で
実際に import してはいけない（gevent の再帰エラーになる）。そこで AST で
構造と、-script が叩くエンドポイントが実 API に存在するかを確認する。
"""

import ast
import re
from pathlib import Path

LOCUSTFILE = Path(__file__).with_name("locustfile.py")
ROUTERS_DIR = Path(__file__).resolve().parents[2] / "src" / "backend" / "routers"


def _locustfile_tree() -> ast.Module:
    return ast.parse(LOCUSTFILE.read_text(encoding="utf-8"))


def test_locustfile_exists_and_parses():
    assert LOCUSTFILE.exists(), f"{LOCUSTFILE} がありません"
    _locustfile_tree()  # SyntaxError が出れば失敗


def test_defines_a_user_class_with_tasks():
    tree = _locustfile_tree()
    user_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and any(_base_name(b).endswith("HttpUser") for b in node.bases)
    ]
    assert user_classes, "HttpUser を継承したクラスが定義されていません"

    has_task = any(
        isinstance(item, ast.FunctionDef)
        and any(_decorator_name(d) == "task" for d in item.decorator_list)
        for cls in user_classes
        for item in cls.body
    )
    assert has_task, "@task が付いたメソッドがありません"


def test_referenced_endpoints_exist_in_backend():
    """locustfile が叩くパスが実 API として存在すること（架空 API の防止）。"""
    tree = _locustfile_tree()
    # docstring は説明のためにパスを書いているだけなので対象から除外する
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    docstrings.discard(None)

    # f-string は Constant 断片に分解されるため、"/api/novel/" のような
    # 部分文字列が独立した定数として現れる。そこは対象外にする。
    fstring_parts = {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in node.values
        if isinstance(part, ast.Constant)
    }

    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value in docstrings or id(node) in fstring_parts:
            continue
        if node.value.startswith("/api/"):
            called.add(node.value)

    assert called, "locustfile が叩いている /api/ エンドポイントがありません"

    # バックエンド側の登録済みパス（プレフィックス + パス）を全文収集
    registered: set[str] = set()
    for router in ROUTERS_DIR.glob("*.py"):
        rtree = ast.parse(router.read_text(encoding="utf-8"))
        prefix = ""
        for node in ast.walk(rtree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "router" for t in node.targets
            ):
                if isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            prefix = str(kw.value.value)
        for node in ast.walk(rtree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and isinstance(dec.func.value, ast.Name)
                        and dec.func.value.id == "router"
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                    ):
                        path = str(dec.args[0].value)
                        registered.add(prefix + path)
                        # パスパラメータをワイルドカードに丸めた形も登録する
                        registered.add(prefix + re.sub(r"\{[^}]+\}", "x", path))

    unknown = sorted(p for p in called if p not in registered)
    assert not unknown, f"バックエンドに存在しないエンドポイントを叩いています: {unknown}"


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""
