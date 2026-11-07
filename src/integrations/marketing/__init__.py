"""Marketing services package.

マーケティング関連機能の一元化:
- MarketingAgent: LLM連携マーケティングエージェント (src.agents.marketing)
- MarketingService: 作品データのパッケージング・エクスポート
- スコアラー: CTR / キャッチフレーズ
"""

from src.agents.marketing import MarketingAgent
from src.integrations.marketing.export_package import MarketingService, DEFAULT_FALLBACK
from src.integrations.marketing.ctr_scorer import score_title_ctr
from src.integrations.marketing.catchphrase_scorer import score_catchphrase_ctr
from src.integrations.marketing.trend_syntax_extractor import extract_syntax_features

__all__ = [
    "MarketingAgent",
    "MarketingService",
    "DEFAULT_FALLBACK",
    "score_title_ctr",
    "score_catchphrase_ctr",
    "extract_syntax_features",
]
