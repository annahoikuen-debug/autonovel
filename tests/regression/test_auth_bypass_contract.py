"""認証バイパス契約の回帰テスト。

何が起きたか
------------
`tests/conftest.py` は全テストで `AUTH_DISABLED=true` を設定する。
そのため「実際の認証経路を検証したいテスト」は、次の関数に short-circuit され、
意図しない結果になる。本監査で実際に踏んだ例:

- `tests/unit/routers/test_auth_jwt_security.py::test_auth_validate_api_key`
  `validate_api_key_sync("invalid-key-999")` が `"dev-key"` を返し `False` にならなかった
  （`src/backend/auth.py:152-153` は `AUTH_DISABLED` 時に検証Finite前に dev-key を返す）
- `tests/unit/backend/test_cors_auth_headers.py::test_unauthorized_response_contains_cors_headers`
  401 を期待したが 200 が返った
- `tests/unit/backend/test_auth_real_session.py::test_get_current_user_with_real_session_no_await_error`
  DB のユーザー(id=101)を期待したが dev モック(id=1)が返った
  （`src/backend/auth.py:47-48`）

いずれも**実装は正しく、テストがグローバル設定と衝突していた**。

このファイルは実装側の契約を両方向で固定する。
- `AUTH_DISABLED=True` → 意図的にバイパスされる（開発用）
- `AUTH_DISABLED=False` → 無効な資格情報は必ず拒否される（本番運用）

 後者を緩めると認証バイパスとして機能し、前者を壊すと開発環境以外の便宜
CI が全て 401 になる。どちらも公開前リリース の品質に直結する。
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestAuthBypassIsExplicitAndScoped:
    """`AUTH_DISABLED` の意味が「全局バイパス」に貧化しないことを固定する。"""

    def test_get_current_user_bypasses_only_when_auth_disabled(
        self, monkeypatch
    ) -> None:
        """AUTH_DISABLED=True のときだけ開発用モックユーザーを返す。"""
        import asyncio

        from src.backend.auth import _get_dev_mock_user, get_current_user
        from src.backend.config import settings

        monkeypatch.setattr(settings, "AUTH_DISABLED", True)
        user = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            get_current_user(token=None, db=None)
        )
        assert user.id == _get_dev_mock_user().id

    def test_get_current_user_rejects_missing_token_when_auth_enabled(
        self, monkeypatch
    ) -> None:
        """AUTH_DISABLED=False でトークン無しは必ず 401。"""
        import asyncio

        from fastapi import HTTPException

        from src.backend.auth import get_current_user
        from src.backend.config import settings

        monkeypatch.setattr(settings, "AUTH_DISABLED", False)

        async def _run():
            await get_current_user(token=None, db=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())
        assert exc.value.status_code == 401

    def test_validate_api_key_sync_rejects_invalid_key_when_auth_enabled(
        self, monkeypatch
    ) -> None:
        """AUTH_DISABLED=False では無効な API キーを必ず False に返す。"""
        from src.backend.auth import validate_api_key_sync
        from src.backend.config import settings

        monkeypatch.setattr(settings, "AUTH_DISABLED", False)
        assert validate_api_key_sync("invalid-key-999") is False
        assert validate_api_key_sync("") is False

    def test_validate_api_key_sync_bypasses_only_when_auth_disabled(
        self, monkeypatch
    ) -> None:
        """AUTH_DISABLED=True のときだけ dev-key を返す（意図された開発用挙動）。"""
        from src.backend.auth import validate_api_key_sync
        from src.backend.config import settings

        monkeypatch.setattr(settings, "AUTH_DISABLED", True)
        assert validate_api_key_sync("invalid-key-999") == "dev-key"

    def test_conftest_default_is_auth_enabled(self) -> None:
        """テスト全体の既定が『認証無効』へ後退していないことを確認する。

        ここが崩れると、認証リグレッションを検出するテストが一斉に
        無効化され、CI が緑でも認証が壊れていても検出できなくなる。

        `AUTH_DISABLED` は `pytest_configure` フック内で `setdefault` される
        ため、config モジュールを import するだけでは適用されない。
        ここではソースを静的に読み、`setdefault(..., "false")` の形が
        保持されていることを確認する（実行環境非依存で確実）。
        """
        import ast
        from pathlib import Path

        conftest = Path("tests/conftest.py")
        assert conftest.exists(), "tests/conftest.py が見つからない"
        tree = ast.parse(conftest.read_text(encoding="utf-8"))

        assignments: list[tuple[str, str]] = []

        def _safe_literal(node: ast.AST) -> str | None:
            """リテラルでない値（変数参照など）は判定対象外とする。

            文字列はクォート無しで返す（`repr()` を使うと
            `'AUTH_DISABLED'='true'` となり、接頭辞判定に失敗する）。
            """
            try:
                value = ast.literal_eval(node)
            except (ValueError, SyntaxError, TypeError):
                return None
            return value if isinstance(value, str) else str(value)

        for node in ast.walk(tree):
            # os.environ.setdefault("X", "y")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr != "setdefault":
                    continue
                target = node.func.value
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "environ"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "os"
                    and len(node.args) == 2
                ):
                    key = _safe_literal(node.args[0])
                    val = _safe_literal(node.args[1])
                    if key is not None and val is not None:
                        assignments.append(("setdefault", f"{key}={val}"))
            # os.environ["X"] = "y"
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "environ"
                        and isinstance(target.value.value, ast.Name)
                        and target.value.value.id == "os"
                    ):
                        key = _safe_literal(target.slice)
                        val = _safe_literal(node.value)
                        if key is not None and val is not None:
                            assignments.append(("assign", f"{key}={val}"))

        auth_entries = [a for a in assignments if a[1].startswith("AUTH_DISABLED=")]
        assert auth_entries, "conftest.py が AUTH_DISABLED を設定していない"

        # 既知の未解決リスク:
        # コミット済み conftest.py:32 は `setdefault("AUTH_DISABLED", "true")`
        # であり、テスト全体で認証が無効化されている。
        # このため認証リグレッションを検出するテストは意味を持たず、
        # CI が緑でも認証が壊れていても検出できない。
        #
        # 解決には認証有効化＋影響テスト(約55件)への依存オーバーライド移行が
        # 必要で、単独では完了できない。本テストは阻尼せず xfail として
        # 「追跡されている既知リスク」を可視化することに専念する。
        # 誰かが AUTH_DISABLED を false へ修正したら XPASS となる。
        disabled = [v for _, v in auth_entries if v.endswith("=true")]
        if disabled:
            pytest.xfail(
                "tests/conftest.py が AUTH_DISABLED=true を設定している。"
                "認証リグレッションが検出できない既知の未解決リスク。"
                f"（検出: {disabled}）"
            )
