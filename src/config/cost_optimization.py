
import os
from typing import Any

# 1MトークンあたりのUSD単価 (2026年時点想定)
MODEL_PRICING = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached_input": 0.025},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00, "cached_input": 0.08},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "cached_input": 0.30},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075},
}

ROUTING_TIERS = {
    "tier1_light": "gemini-2.0-flash",      # 構成・ブレスト・要約・監査
    "tier2_standard": "claude-3-5-haiku",   # 日常シーン・展開回の執筆
    "tier3_premium": "claude-3-5-sonnet",   # クライマックス・第1話・重要伏線回収
}


class UnknownModelPricingError(KeyError):
    """``MODEL_PRICING`` に無いモデルが要求されたことを表す。

    T6 Step 5: 従来 `TokenTracker.estimate_cost_usd` は未知モデルに対して
    黙って 0.0 を返していた。モデルルーティングを有効化すると、
    未登録モデルへ切り替わった瞬間に**コスト計測が $0 として無言化する**ため、
    「ルーティングの効果を数値で検証できない」状態になる。
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(
            f"モデル {model_name!r} の価格が MODEL_PRICING に登録されていません。"
            f" 登録済み: {sorted(MODEL_PRICING)}"
        )


def resolve_pricing(model_name: str) -> dict[str, float]:
    """モデル名から 1M トークンあたりのUSD単価を返す。

    Raises:
        UnknownModelPricingError: 未知モデルの場合（0.0 を返さない）
    """
    if not model_name:
        raise UnknownModelPricingError(model_name)
    pricing = MODEL_PRICING.get(model_name)
    if pricing is None:
        raise UnknownModelPricingError(model_name)
    return pricing

#: モデルID → tier 名の逆引き（token_tracker の tier バケット用）
TIER_BY_MODEL: dict[str, str] = {
    model: tier for tier, model in ROUTING_TIERS.items()
}

#: 機能フラグ: tier ルーティングの既定値（段階導入のため OFF）。
#: 環境変数 ``ENABLE_MODEL_ROUTING`` で上書きできる。
DEFAULT_ENABLE_MODEL_ROUTING = False

_TRUTHY = ("1", "true", "yes", "on")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def is_model_routing_enabled() -> bool:
    """tier ルーティング（Step 26/27）が有効かどうかを返す。

    既定は OFF（``ENABLE_MODEL_ROUTING=true`` で段階導入する）。
    OFF の間は従来どおり ``resolve_model_for_purpose`` の結果が使われるため、
    ロールバックは環境変数を落とすだけで完了する。
    """
    return _env_flag("ENABLE_MODEL_ROUTING", DEFAULT_ENABLE_MODEL_ROUTING)


def is_climax_episode(
    ep_num: int | None = None,
    payload: dict[str, Any] | None = None,
    writing_context: dict[str, Any] | None = None,
) -> bool:
    """クライマックス（＝tier3_premium 対象）かどうかを判定する。

    判定対象（Step 27 の「tier3 を実効化」要件）:

    1. 第1話（和规范としての入口话）
    2. フラグで明示されたクライマックス
    3. 重要伏線の回収（payoff）
    4. pro / enterprise プラン

    Args:
        ep_num: エピソード番号
        payload: リクエスト payload（``is_climax`` / ``plan`` 等）
        writing_context: 執筆コンテキスト（``is_climax`` / ``is_foreshadowing_payoff`` 等）

    Returns:
        tier3_premium を適用すべきなら True
    """
    payload = payload or {}
    writing_context = writing_context or {}

    if ep_num is not None and int(ep_num) == 1:
        return True

    for source in (payload, writing_context):
        for key in ("is_climax", "climax", "is_turning_point"):
            if _truthy(source.get(key)):
                return True
        for key in (
            "is_foreshadowing_payoff",
            "foreshadowing_payoff",
            "is_important_foreshadowing_payoff",
        ):
            if _truthy(source.get(key)):
                return True

    plan = str(
        writing_context.get("user_plan") or payload.get("user_plan") or payload.get("plan") or "free"
    ).lower()
    return plan in ("pro", "enterprise")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return bool(value)


def resolve_episode_tier(
    ep_num: int | None = None,
    payload: dict[str, Any] | None = None,
    writing_context: dict[str, Any] | None = None,
    user_plan: str = "free",
) -> str:
    """1話ぶんの執筆が担当する tier 名を返す。

    クライマックス/第1話/重要伏線回収は ``tier3_premium``、それ以外は
    ``tier2_standard`` を返す。構成・監査系は呼び出し側で
    ``tier1_light`` に固定する。
    """
    plan = str(user_plan or "free").lower()
    resolved_plan = plan
    if plan == "free":
        source = payload or writing_context or {}
        resolved_plan = str(source.get("user_plan") or source.get("plan") or "free").lower()

    if is_climax_episode(ep_num=ep_num, payload=payload, writing_context=writing_context) or (
        resolved_plan in ("pro", "enterprise")
    ):
        return "tier3_premium"
    return "tier2_standard"


def tier_for_model(model_name: str | None) -> str | None:
    """モデルIDから tier 名を逆引きする（未知のモデルは ``None``）。"""
    if not model_name:
        return None
    return TIER_BY_MODEL.get(model_name)
