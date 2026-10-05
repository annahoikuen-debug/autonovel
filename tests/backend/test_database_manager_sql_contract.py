"""`DatabaseManager` の SQL 受け付け契約と、Protocol 型の一致を固定するゲート。

何が起きたか
------------
2026-10-05 の公開前残存タスク調査で、`src/core/interfaces.py` の
`DatabaseManagerProtocol` が `query: str` と宣言している一方、
実装（`src/backend/database/core.py`）は**生の文字列 SQL を拒否**していた
（`TypeError`）。つまり型契約が実装と矛盾していた。

さらに `fetch_lastrowid` だけは raw str 拒否が**漏れており**、
`exec_driver_sql()` に生文字列を渡していた（パラメータをバインドしないため
実害のある注入面）。同一クラス内で契約が食い違っていた。

本ファイルは
1. raw string 拒否という**意図**を（実装できる／できないの両方で）固定し
2. Protocol の型注釈が実装と一致することを固定する
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import typing

import pytest

RAW_STRING_REJECTING_METHODS = ("execute", "fetch_one", "fetch_all", "fetch_lastrowid")


@pytest.mark.integration
class TestRawStringIsRejected:
    """生文字列 SQL が全メソッドで一貫して拒否されること。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method_name", RAW_STRING_REJECTING_METHODS)
    async def test_rejects_raw_string(self, method_name: str) -> None:
        """4 メソッドすべてが生文字列を TypeError で拒否する。

        `fetch_lastrowid` だけ拒否していなかったため、ここに含めている。
        将来さらに新しい生 SQL メソッドが追加された場合も、
        この parametrize に追加しない限り検出できない点には注意。
        """
        from src.backend.database.core import DatabaseManager

        mgr = DatabaseManager("sqlite:///:memory:")
        method = getattr(mgr, method_name)

        with pytest.raises(TypeError) as exc:
            await method("SELECT 1")
        assert "no longer accepts raw strings" in str(exc.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method_name", RAW_STRING_REJECTING_METHODS)
    async def test_error_message_names_the_method(self, method_name: str) -> None:
        """エラーメッセージがメソッド名を含むこと（利用者误解の防止）。"""
        from src.backend.database.core import DatabaseManager

        mgr = DatabaseManager("sqlite:///:memory:")
        method = getattr(mgr, method_name)

        with pytest.raises(TypeError) as exc:
            await method("SELECT 1")
        assert method_name in str(exc.value), (
            f"エラーメッセージがメソッド名を含まない: {exc.value}"
        )


@pytest.mark.integration
class TestProtocolMatchesImplementation:
    """Protocol の型契約が実装と一致すること。"""

    @pytest.mark.parametrize("method_name", ("fetch_one", "fetch_all", "execute"))
    def test_protocol_does_not_declare_raw_str(self, method_name: str) -> None:
        """Protocol が `str` を引数に宣言していないこと。

        以前は `query: str` と宣言しており、実装は str を拒否していたため
        型検査が意味を失っていた。
        """
        from src.core.interfaces import DatabaseManagerProtocol

        sig = typing.get_type_hints(
            getattr(DatabaseManagerProtocol, method_name)
        )
        query_type = sig.get("query") or sig.get("sql")
        assert query_type is not None, f"{method_name} に query/sql の型注釈が無い"

        # str そのもの、または str を含む Union は不可
        def _contains_str(tp) -> bool:
            if tp is str:
                return True
            args = typing.get_args(tp)
            return any(_contains_str(a) for a in args)

        assert not _contains_str(query_type), (
            f"{method_name} の引数型に str が含まれている: {query_type}。"
            "実装は生文字列を拒否するため、Protocol にも含められない"
        )

    def test_protocol_declares_text_clause(self) -> None:
        """Protocol が `TextClause` を要求していること。"""
        from src.core.interfaces import DatabaseManagerProtocol

        sig = typing.get_type_hints(DatabaseManagerProtocol.fetch_one)
        rendered = str(sig.get("query"))
        assert "TextClause" in rendered, (
            f"Protocol が TextClause を要求していない: {rendered}"
        )

    @pytest.mark.asyncio
    async def test_enqueue_write_also_rejects_raw_string(self) -> None:
        """`enqueue_write`（`execute` のシム）も生文字列を拒否すること。

        `enqueue_write` は `execute()` に委譲する後方互換シムだが、
        **自分で拒否していないと**、拒否契約がメソッドごとに
        食い違う（= T8 で直した `fetch_lastrowid` と同種の不整合）。
        """
        from src.backend.database.core import DatabaseManager

        mgr = DatabaseManager("sqlite:///:memory:")
        with pytest.raises(TypeError) as exc:
            await mgr.enqueue_write("SELECT 1")
        assert "no longer accepts raw strings" in str(exc.value)

    def test_rejection_guards_are_implemented_in_every_method(self) -> None:
        """4 つの主メソッドすべてに `isinstance(sql, str)` の拒否ガードがあること。

        `enqueue_write` のような**委譲シム**は自分でガードを持たないが、
        委譲先がガードしているため実行時には拒否される
        （`test_enqueue_write_also_rejects_raw_string` で実証済み）。
        そのためシムは本検査の対象外。
        """
        from src.backend.database.core import DatabaseManager

        for name in RAW_STRING_REJECTING_METHODS:
            body = _method_body(getattr(DatabaseManager, name))

            has_guard = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
                and any(
                    # `str` はソース上は組み込み名なので AST 上は
                    # Constant ではなく Name として現れる
                    (isinstance(a, ast.Name) and a.id == "str")
                    or (isinstance(a, ast.Constant) and a.value == "str")
                    for a in node.args
                )
                for stmt in body
                for node in ast.walk(stmt)
            )
            assert has_guard, (
                f"{name} に `isinstance(sql, str)` の拒否ガードが無い。"
                "生文字列が通過するため、拒否契約がメソッド間で食い違う"
            )


def _method_body(func) -> list:
    """関数の AST 返す（docstring を除く）。

    `inspect.getsource` はインデント付きかつ docstring を含むため、
    そのまま文字列検索すると「docstring に書いた文字列」を
    実装と誤判定してしまう（実際に一度落ちた）。
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    fn = tree.body[0]
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


@pytest.mark.integration
class TestFetchLastrowidUsesBoundParameters:
    """`fetch_lastrowid` が `exec_driver_sql` を通らないこと。

    `exec_driver_sql` はプレースホルダをバインドせず文字列を直接渡すため、
    他のメソッドが `text()` で避けているものと同じ注入面を持つ。
    """

    def test_source_does_not_use_exec_driver_sql(self) -> None:
        from src.backend.database.core import DatabaseManager

        body = _method_body(DatabaseManager.fetch_lastrowid)
        called = {
            node.func.attr
            for stmt in body
            for node in ast.walk(stmt)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "exec_driver_sql" not in called, (
            "fetch_lastrowid が exec_driver_sql を使っている。"
            "他のメソッドと同様に conn.execute() を使うべき"
        )
        assert "execute" in called, "fetch_lastrowid が execute を呼んでいない"

    @pytest.mark.asyncio
    async def test_accepts_text_clause(self) -> None:
        """`text()` を渡した場合は拒否されないこと（正常系の正面確認）。"""
        from sqlalchemy import text
        from unittest.mock import AsyncMock, Mock

        from src.backend.database.core import DatabaseManager

        mgr = DatabaseManager("sqlite:///:memory:")

        mock_result = Mock()
        mock_result.lastrowid = 42
        mock_conn = Mock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mgr.engine = Mock()
        mgr.engine.begin = Mock(return_value=mock_conn)

        result = await mgr.fetch_lastrowid(text("INSERT INTO t VALUES (1)"))
        assert result == 42
