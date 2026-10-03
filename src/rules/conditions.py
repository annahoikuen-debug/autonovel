"""条件関数レジストリ (Week 2 Step 5)。

ルールの適用条件として使用できる事前定義関数を提供する。
YAML から文字列式を eval せず、このレジストリ経由で関数を参照する。
"""
from __future__ import annotations

import inspect
import logging
from typing import Callable, Dict

from src.rules.emotional_rules import PlotContext

logger = logging.getLogger(__name__)

ConditionFunc = Callable[[PlotContext], bool]


class ConditionRegistry:
    """条件関数レジストリ。

    ``@condition_registry.register("name")`` でデコレートした関数を
    文字列名で参照可能にする。
    """

    def __init__(self) -> None:
        self._conditions: Dict[str, ConditionFunc] = {}

    def register(self, name: str) -> Callable[[ConditionFunc], ConditionFunc]:
        """条件関数を名前付きで登録するデコレータ。"""

        def decorator(func: ConditionFunc) -> ConditionFunc:
            self._conditions[name] = func
            return func

        return decorator

    def get(self, name: str) -> ConditionFunc:
        """名前から条件関数を取得 (未登録なら KeyError)。"""
        if name not in self._conditions:
            raise KeyError(f"Unknown condition: {name!r}")
        return self._conditions[name]

    def has(self, name: str) -> bool:
        """名前が登録済みか判定。"""
        return name in self._conditions

    def names(self) -> list[str]:
        """登録済み条件名一覧。"""
        return sorted(self._conditions.keys())

    def create(self, name: str, **params) -> ConditionFunc:
        """名前とパラメータから部分適用済み条件関数を生成。

        例: ``create("relationship_above", threshold=0.5)``

        パラメータ名は **生成時** に検証する。部分適用ラッパの生成自体は
        例外を投げないため、typo は評価時 (例外が握り潰され常に False) にしか
        表面化せず、ルールの黙示的な無効化を起こしていた。
        """
        func = self.get(name)
        self.validate_params(name, func, params)
        return lambda ctx: func(ctx, **params)  # type: ignore[call-arg]

    @staticmethod
    def validate_params(name: str, func: ConditionFunc, params: Dict[str, object]) -> None:
        """パラメータ名をターゲットのシグネチャと照合する。

        Args:
            name: 条件名 (ログ・例外メッセージ用)
            func: 実条件関数
            params: 渡そうとしているパラメータ

        Raises:
            ValueError: 未定義のパラメータ名が含まれる場合
        """
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):  # pragma: no cover - 内蔵関数のsignature不可
            return

        parameters = list(signature.parameters.values())
        # 第1引数は PlotContext
        positional = parameters[1:] if parameters else []
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
            return

        valid = {p.name for p in positional}
        accepts_varargs = any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in positional)
        invalid = [key for key in params if key not in valid]
        if invalid and not accepts_varargs:
            message = (
                f"Condition {name!r} received unknown parameter(s) {sorted(invalid)}; "
                f"valid parameters: {sorted(valid) or '(none)'}"
            )
            logger.error(message)
            raise ValueError(message)


# モジュールレベルのシングルインスタンス
condition_registry = ConditionRegistry()


@condition_registry.register("relationship_above")
def relationship_above(ctx: PlotContext, threshold: float = 0.5) -> bool:
    """関係レベルが閾値以上か判定。"""
    return ctx.relationship_level >= threshold


@condition_registry.register("tension_above")
def tension_above(ctx: PlotContext, threshold: float = 0.5) -> bool:
    """直前の緊張度が閾値以上か判定。"""
    return ctx.previous_tension >= threshold


@condition_registry.register("previous_event_was")
def previous_event_was(ctx: PlotContext, event_type: str = "") -> bool:
    """直前のイベントが指定タイプだったか判定。"""
    # custom_data["previous_event_type"] にエンジンが記録する前提
    prev = ctx.custom_data.get("previous_event_type")
    if prev is None:
        return False
    if hasattr(prev, "value"):
        prev = prev.value
    return str(prev).lower() == str(event_type).lower()


@condition_registry.register("custom_flag")
def custom_flag(ctx: PlotContext, flag_name: str = "") -> bool:
    """カスタムフラグが立っているか判定。"""
    return bool(ctx.custom_data.get(flag_name))


__all__ = [
    "ConditionRegistry",
    "ConditionFunc",
    "condition_registry",
    "relationship_above",
    "tension_above",
    "previous_event_was",
    "custom_flag",
]
