"""生成系エンドポイント用の事前クレジット残高チェック。

タスク投入 (enqueue) の**前**に残高を検証し、残高不足なら 402 で拒否する。

背景: ``require_credits`` はどこからも import されない「死にコード」であり、
生成エンドポイントには課金ガドが一切接続されていなかった（レビュー指摘 H4）。
結果としてサーバー側 LLM キーで無課金実行が可能だった。

注意:
- 本モジュールは**チェックのみ**で控除しない。控除は生成タスク
  (``generation_tasks``) が ``_sync_deduct_credits`` で行う。
- 要求クレジットは ``CreditService.COST_PER_EPISODE`` に一致させる。
  タスク側が 1 を控除するのにルーター側が 10 を要求すると、残高 1〜9 の
  ユーザーが正当なタスク投入まで拒否される（過剰制御）になる。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.services.billing.credit_service import CreditService

__all__ = [
    "require_generation_credits",
    "check_generation_credits",
    "check_credits_balance",
    "check_illustration_credits",
]


def check_credits_balance(user: Any, required: int) -> int:
    """``user`` が ``required`` クレジット以上の残高を持つことを検証する。

    残高不足なら 402 (``INSUFFICIENT_CREDITS``) を送出する。
    残高が取得できない場合 (開発用モック・カラム未設定など) は
    検証をスキップし、タスク投入を妨げない (fail-open)。
    """
    balance = getattr(user, "credits", None)
    if balance is None:
        # 所有者は特定済みだが残高が読めないケース (開発モック等)。
        # fail-open で続行する (控除はタスク側が担う)。
        return required
    try:
        insufficient = int(balance) < int(required)
    except (TypeError, ValueError):
        return required
    if insufficient:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error_code": "INSUFFICIENT_CREDITS",
                "required": int(required),
                "balance": int(balance),
            },
        )
    return required


def check_generation_credits(user: Any) -> int:
    """``user`` が生成タスクを投入できる残高を持っているか検証する。

    残高不足なら 402 を送出。残高が取得できない場合 (開発用モック・
    カラム未設定など) は検証をスキップし、タスク投入を妨げない。
    """
    return check_credits_balance(user, CreditService.COST_PER_EPISODE)


def check_illustration_credits(user: Any, num_images: int = 1) -> int:
    """挿絵生成 (``COST_PER_ILLUSTRATION`` × 枚数) 分の残高を検証する。

    残高不足なら 402 を送出。挿絵はテキスト執筆とは単価が異なるため
    枚数を明示的に受け取り、単価との積を要求クレジットとする。
    """
    try:
        images = max(0, int(num_images))
    except (TypeError, ValueError):
        images = 1
    return check_credits_balance(user, CreditService.COST_PER_ILLUSTRATION * images)


def require_generation_credits():
    """FastAPI 依存ファクトリ: 生成タスク投入前の残高チェックを要求する。

    使い方::

        @router.post("/generate")
        async def generate(
            ...,
            current_user: User = Depends(get_current_user),
            _credits: int = Depends(require_generation_credits()),
        ):
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> int:
        return check_generation_credits(current_user)

    return dependency
