"""矛盾レポート生成サービス - 後方互換 shim。

F4 フェーズ: 実装は src/domain/services/conflict_report_service.py に移設。
このモジュールは re-export 用 shim として残す。
"""

from __future__ import annotations

from src.domain.services.conflict_report_service import (  # noqa: F401
    ConflictItem,
    ConflictReport,
    ConflictReportService,
)
