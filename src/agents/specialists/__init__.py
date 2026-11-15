"""Phase 2: 8 Specialist Auditors package (v5.0 Unified Architecture).

Note on v5.0 Refactoring:
8並列オーディター（Consistency, Emotion, Style等）は、アテンション希釈とコスト爆発を防止するため、
二層ハイブリッド監査エンジン `UnifiedAuditor`（静的ルール解析0ms + 単一LLM定性判定）へ集約されました。
既存コードとの後方互換性のため旧クラスもエクスポートされていますが、新規開発では `UnifiedAuditor` を使用してください。
"""

from src.agents.specialists.unified_auditor import UnifiedAuditor
from src.agents.specialists.adapter import AuditAggregatorNode

__all__ = [
    "UnifiedAuditor",
    "AuditAggregatorNode",
]
