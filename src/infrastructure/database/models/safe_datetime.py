"""日時型デコレータ (infrastructure 層)。

TRACK-A5: `src/backend/database/models.py` から `SafeDateTime` を
`src/infrastructure/database/models/safe_datetime.py` へ実体移動。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class SafeDateTime(TypeDecorator):
    """datetime または unix timestamp (int/float) の両方を受け付けるカラム型の型デコレータ。"""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        return value
