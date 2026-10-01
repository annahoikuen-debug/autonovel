"""router に book_id を取る全 route が所有者検証を行っていることの保証。

対象: src/backend/routers/{structure,prompt_versions,prompt_compare}.py
"""
from __future__ import annotations

import inspect

import pytest

ROUTER_FILES = [
    "src/backend/routers/structure.py",
    "src/backend/routers/prompt_versions.py",
    "src/backend/routers/prompt_compare.py",
]


@pytest.mark.parametrize("path", ROUTER_FILES)
def test_router_requires_current_user(path):
    """router 定義に get_current_user 依存があること。"""
    src = open(path, encoding="utf-8").read()
    assert "get_current_user" in src, f"{path} に get_current_user がない"
    assert "verify_book_ownership" in src, f"{path} に verify_book_ownership がない"


@pytest.mark.parametrize("path", ROUTER_FILES)
def test_every_book_scoped_handler_calls_ownership_check(path):
    """book_id を受け取るハンドラが全て所有者検証している（機械チェック）。"""
    import ast

    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        args = [a.arg for a in node.args.args]
        if "book_id" not in args:
            continue
        body_src = ast.get_source_segment(open(path, encoding="utf-8").read(), node) or ""
        assert "verify_book_ownership" in body_src, (
            f"{path}:{node.lineno} {node.name}() は book_id を受けるが所有者検証を呼ばない"
        )
