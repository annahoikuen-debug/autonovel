import json
import os
from typing import List

from src.backend.config import settings


def get_allowed_origins() -> List[str]:
    """環境変数からCORS許可originリストを取得"""
    origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not origins_env:
        # デフォルトは開発用。環境の変更を反映させるため都度 Settings を構築する
        # (SSOT: src.backend.config.settings.CORS_ORIGINS)
        return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    # Attempt to parse JSON array first (e.g., '["http://example.com"]')
    try:
        parsed = json.loads(origins_env)
        if isinstance(parsed, list):
            return [o.strip() for o in parsed if isinstance(o, str) and o.strip()]
    except json.JSONDecodeError:
        pass
    # Fallback to comma‑separated string
    return [o.strip() for o in origins_env.split(",") if o.strip()]
