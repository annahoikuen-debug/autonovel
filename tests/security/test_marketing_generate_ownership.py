"""Step 4 (H3): marketing.py の /api/marketing/generate に所有権検証が追加されたことを検証。

H3: /api/marketing/generate が verify_book_ownership を呼ばずに他者の book_id で
LLM ワークフローを実行できる IDOR を修正。
"""
from __future__ import annotations

import inspect

from src.backend.routers import marketing


def test_marketing_generate_calls_verify_book_ownership():
    """marketing.generate_marketing が verify_book_ownership を呼ぶ（H3）。"""
    src = inspect.getsource(marketing.generate_marketing)
    assert "verify_book_ownership" in src, (
        "marketing.generate_marketing に verify_book_ownership がない (H3)"
    )
