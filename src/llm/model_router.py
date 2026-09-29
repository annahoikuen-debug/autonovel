from __future__ import annotations

from typing import Any

from src.config.cost_optimization import ROUTING_TIERS

# デフォルトモデルマッピング（必要に応じて追加）
_DEFAULTS = {
    "planning": "gemini-3.5-flash-lite",
    "plot_expansion": "gemma-4-31b-it",
    "writing": "gemma-4-31b-it",
    "climax": "gemma-4-31b-it",
    "fallback": "gemma-4-31b-it",
    "ultra_stable": "gemma-4-31b-it",
    "audit": "gemini-3.5-flash-lite",
    "marketing": "gemini-3.5-flash-lite",
}

# select_model() で「用途」として解釈するキー群。
# これ以外の文字列はリテラルのモデルIDとして扱う。
_PURPOSES = set(_DEFAULTS.keys())

# OpenAI互換（GPT, Claude-via-OpenRouter, Llama, Mistral, Qwen,
# DeepSeek, Command, Gemini-via-OpenRouter 等）とみなすプレフィックス/キーワード。
# OpenRouter のモデルIDは "anthropic/claude-3.5-sonnet" のように "/" を含む。
_OPENAI_COMPAT_HINTS = (
    "gpt",
    "claude",
    "llama",
    "mistral",
    "qwen",
    "deepseek",
    "command",
    "anthropic",
    "openrouter",
    "sonar",
    "glm",
    "yi-",
    "phi",
    "cohere",
    "meta/",
    "mistralai/",
    "google/",
    "openai/",
    "anthropic/",
    "deepseek/",
    "qwen/",
)


def is_openai_compatible(model_name: str) -> bool:
    """モデル名がOpenAI互換API（OpenRouter等）経由で呼び出すべきかを判定する。"""
    if not model_name:
        return False
    # OpenRouter 等は "org/model" 形式のモデルIDを使う
    if "/" in model_name:
        return True
    lowered = model_name.lower()
    return any(hint in lowered for hint in _OPENAI_COMPAT_HINTS)


def select_model(purpose: str = "writing") -> str:
    """目的に応じたモデル名を返す。

    環境変数や `config.streamlit_adapter` の上書き設定があればそちらを優先。
    既知の「用途」でなければ、渡された文字列をそのままモデルIDとして返す。
    """
    # 用途でない（リテラルのモデルID等）場合はそのまま返す
    if purpose not in _PURPOSES:
        return purpose

    # 設定から取得を試みる (SSOT: GlobalConfigModel / settings.toml)
    key = f"model_{purpose}"
    try:
        from config.project_context import get_config

        value = getattr(get_config(), key, None)
        if value:
            return str(value)
    except Exception:
        pass
    return _DEFAULTS.get(purpose, "gemini-3.5-flash-lite")


def resolve_model(value: str) -> str:
    """LLM呼び出し時に渡された値（用途 or モデルID）を実際のモデル名に解決する。

    - 既知の用途 ("writing" 等) なら select_model() で設定値を解決
    - それ以外（"gemini-2.0-flash", "anthropic/claude-3.5-sonnet" 等）はそのまま返す
    """
    if value in _PURPOSES:
        return select_model(value)
    return value


def resolve_model_for_purpose(purpose: str, override_config: Any | None = None) -> str:
    """用途 (purpose) に応じたモデル名を解決する。

    優先順位:
    1. override_config の用途別指定 (model_planning, model_writing, model_audit, model_embedding 等)
    2. override_config の全体指定 (model_name)
    3. サーバー既定値 (select_model)
    """
    if override_config:
        # dict または Pydantic モデルの両方に対応
        val_purpose = None
        val_global = None
        key_purpose = f"model_{purpose}"
        if isinstance(override_config, dict):
            val_purpose = override_config.get(key_purpose)
            val_global = override_config.get("model_name")
        else:
            val_purpose = getattr(override_config, key_purpose, None)
            val_global = getattr(override_config, "model_name", None)

        if val_purpose:
            return str(val_purpose)
        if val_global:
            return str(val_global)

    return select_model(purpose)


#: 軽い tier を適用するタスク種別（構成・監査・スクリーニング）
LIGHT_TASK_TYPES = ("planning", "audit", "screening", "config", "summary", "plot_expansion")


def resolve_tier(
    task_type: str,
    is_climax: bool = False,
    user_plan: str = "free",
    ep_num: int | None = None,
    is_foreshadowing_payoff: bool = False,
) -> str:
    """タスク種別と要求品質から **tier 名**（tier1_light / ...）を返す。

    v6 / Step 27: 従来は ``is_climax`` のみが上位モデルの条件だったため、
    本番経路で実際に算出される「第1話・クライマックス・重要伏線回収」を
    ここに集約し、tier 割り当てを実効化した。

    Args:
        task_type: タスク種別（``planning`` / ``audit`` / ``writing`` など）
        is_climax: クライマックス話か
        user_plan: プラン（``free`` / ``pro`` / ``enterprise``）
        ep_num: エピソード番号（第1話なら tier3）
        is_foreshadowing_payoff: 重要伏線回収か
    """
    if task_type in LIGHT_TASK_TYPES:
        return "tier1_light"

    if is_climax or is_foreshadowing_payoff:
        return "tier3_premium"
    if ep_num is not None and int(ep_num) == 1:
        return "tier3_premium"
    if user_plan in ["pro", "enterprise"]:
        return "tier3_premium"
    return "tier2_standard"


def resolve_optimized_model(
    task_type: str,
    is_climax: bool = False,
    user_plan: str = "free",
    ep_num: int | None = None,
    is_foreshadowing_payoff: bool = False,
) -> str:
    """
    リクエストの要求品質とタスク種別から最適モデルを動的解決。
    3層ハイブリッドルーティングを実装。
    """
    return ROUTING_TIERS[resolve_tier(task_type, is_climax, user_plan, ep_num, is_foreshadowing_payoff)]
