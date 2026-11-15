"""マーケティング系 API の集約モジュール。

PLAN_Q3: 旧 src.services.marketing shim は削除済み。各シンボルは
以下の実体モジュールから再エクスポートする:

* MarketingAgent  → src.agents.marketing
* MarketingService / DEFAULT_FALLBACK → src.integrations.marketing.export_package
* score_title_ctr → src.integrations.marketing.ctr_scorer
* score_catchphrase_ctr → src.integrations.marketing.catchphrase_scorer
* extract_syntax_features → src.integrations.marketing.trend_syntax_extractor
"""

from __future__ import annotations

from src.agents.marketing import MarketingAgent  # noqa: F401
from src.integrations.marketing.catchphrase_scorer import (  # noqa: F401
    score_catchphrase_ctr,
)
from src.integrations.marketing.export_package import (  # noqa: F401
    DEFAULT_FALLBACK,
    MarketingService,
)
from src.integrations.marketing.ctr_scorer import score_title_ctr  # noqa: F401
from src.integrations.marketing.trend_syntax_extractor import (  # noqa: F401
    extract_syntax_features,
)

__all__ = [
    "MarketingAgent",
    "MarketingService",
    "DEFAULT_FALLBACK",
    "score_title_ctr",
    "score_catchphrase_ctr",
    "extract_syntax_features",
]
