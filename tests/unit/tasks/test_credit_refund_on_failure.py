"""Step 9 (H8): クレジット返金の UnboundLocalError 修正。

H8: generate_chapter_task / generate_chapter_orchestrated_task で
credit_service が _deduct() クロージャ内でのみ代入され、返金ブロックが
UnboundLocalError で不発していた。condition から credit_service is not None を削除し、
失敗時必ず返金するように修正。
"""
from __future__ import annotations

import inspect

import src.backend.tasks.generation_tasks as gt


def test_credit_refund_condition_without_credit_service():
    """返金条件から credit_service is not None が削除されている（H8）。
    credit_service は _deduct() クロージャ内ローカルなので、ここでは常に None
    となり、これまで返金が不発だった。
    """
    src = inspect.getsource(gt)
    # 2 つのタスク関数の両方で修正済みであること
    for fn_name in ("generate_chapter_task", "generate_chapter_orchestrated_task"):
        fn_src = inspect.getsource(getattr(gt, fn_name).func)
        # 返金条件に credit_service is not None が含まれていない
        assert "credits_deducted and credit_service is not None" not in fn_src, (
            f"{fn_name} に credit_service is not None が残っている (H8)"
        )
        # credits_deducted and user_id is not None の条件は残っている
        assert "credits_deducted and user_id is not None" in fn_src, (
            f"{fn_name} に credits_deducted and user_id is not None の条件がない (H8)"
        )
