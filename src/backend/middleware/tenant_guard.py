"""書籍所有権ガードの互換モジュール（非推奨）。

実装は `src.backend.security.owner_guard.verify_book_ownership` に一本化されている。
ここでは再エクスポートのみを行い、ロジックを重複させない。
"""
from __future__ import annotations

from src.backend.security.owner_guard import verify_book_ownership

__all__ = ["verify_book_ownership"]
