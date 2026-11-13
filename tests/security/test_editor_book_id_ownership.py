"""Step 4 (H2): editor.py の book_id エンドポイントに所有権検証が追加されたことを検証。

H2: /api/editor/ask-bible, /audit-consistency, /next-beats が
verify_book_ownership を呼ばずに他者の本のデータを読み取れる IDOR を修正。
"""
from __future__ import annotations

import inspect

from src.backend.routers import editor


def test_editor_routes_call_verify_book_ownership():
    """editor.py の book_id エンドポイントが全て verify_book_ownership を呼ぶ（H2）。"""
    src = inspect.getsource(editor)
    # 3 つのハンドラそれぞれに verify_book_ownership が含まれることを確認
    for handler in ("ask_bible", "audit_consistency", "generate_next_beats"):
        handler_src = inspect.getsource(getattr(editor, handler))
        assert "verify_book_ownership" in handler_src, (
            f"editor.{handler} に verify_book_ownership がない (H2)"
        )
    assert "import verify_book_ownership" in src or "from src.backend.security.owner_guard import verify_book_ownership" in src
