"""常にUTCタイムゾーン付きとして安全に変換するDateTime型。"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class CompatibleDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            # タイムゾーンなしの場合はUTCとみなす
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        # PostgreSQL (asyncpg) は TIMESTAMP WITHOUT TIME ZONE に対して
        # offset-aware datetime を渡すと DataError (can't subtract offset-naive and offset-aware datetimes) で落ちる。
        # UTC 換算後に tzinfo を外した naive UTC としてバインドする。
        if dialect and dialect.name == "postgresql":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
