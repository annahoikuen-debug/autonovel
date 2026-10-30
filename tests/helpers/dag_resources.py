"""DAG スケジューラのテストをマシンの空き RAM から独立させるリソース固定ヘルパ。

`DAGScheduler` のセマフォ容量は `ResourceManager.get_available_ram_mb()`
（psutil の実測値）から算出される。空き RAM が小さい環境では ram_slots が
1 となり、`build_novel_generation_dag()` が要求する ram_mb=1024（=2スロット）の
ノードが **一度も発行されない**。`run_dag()` は `launched == 0` のまま
`asyncio.sleep()` を繰り返し、無限ポーリングでハングする。

実測例（PLAN_J1 W6）:
    available_ram = 594MB, max_ram_ratio = 0.8 → ram_slots = 1
    b1_ep1_write  ram_mb=1024 → 必要 2 スロット → can_schedule = False
    → run_dag が 45 秒超でも完了せず（正常なマシンでは 0.00 秒で全ノード完了）

本ヘルパはテストの目的（6ノード DAG が最後まで実行されること）を検証するために
実測値から切り離すためのものであり、テストを通すための迎合ではない。

注意: 製品側の「要求 RAM が総容量を超えるノードを検出せず無限ループする」挙動は
**未修正**である（テスト側のみ対応。課題として記録済み）。
"""
from __future__ import annotations

from src.backend.tasks.resource_manager import ResourceManager

# 6ノード章生成DAG が要求する最大 ram_mb=1024（=2スロット）を十分に上回る値。
PLENTY_RAM_MB = 16384


def patch_available_ram(monkeypatch, available_ram_mb: int = PLENTY_RAM_MB) -> None:
    """`ResourceManager.get_available_ram_mb` を固定値に差し替える。

    クラスメソッドを差し替えるため、`DAGScheduler()` が内部で
    `ResourceManager()` を生成しても（`run_novel_dag_pipeline_async` の経路も含む）
    同じ効果が及ぶ。function スコープの monkeypatch により自動で元に戻る。
    """
    monkeypatch.setattr(
        ResourceManager,
        "get_available_ram_mb",
        lambda self: available_ram_mb,
    )
