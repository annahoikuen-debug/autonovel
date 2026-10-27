"""CausalNode / CausalEdge と位相順序・依存伝播の回帰テスト（PLAN_W5 Step 5-6）。

`_chain` は「すべてのノードが後続語を持つ鎖」を作る。
（計画書の `_chain` は末尾ノードだけを独立ノードにしており、
`test_topological_order_respects_edges` の `order.index(2) < order.index(5)` と
衝突するため、鎖と独立ノードを別テストに分けた。）
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.services.foreshadowing.causal_dag import (  # noqa: E402
    CausalNode,
    build_dag,
    dependents_of,
    edges_of,
    roots_of,
    topological_order,
)

ROWS = [
    {"id": 1, "target_episode": 8, "status": "planted", "description": "古代の魔導書を拾う"},
    {"id": 2, "target_episode": 12, "status": "planted", "description": "解読に失敗して危機に陥る"},
    {"id": 3, "target_episode": 20, "status": "planted", "description": "賢者と出会い，真相が判明する"},
]


def _chain(n: int) -> list[dict]:
    return [
        {
            "id": i,
            "target_episode": i,
            "status": "planted",
            "description": "後続の結果として現れる",
        }
        for i in range(1, n + 1)
    ]


# ── Step 5: ノードと辺 ────────────────────────────────────────────
def test_build_dag_returns_one_node_per_row():
    nodes = build_dag(ROWS)
    assert len(nodes) == 3
    assert {n.foreshadowing_id for n in nodes} == {1, 2, 3}


def test_nodes_are_immutable():
    nodes = build_dag(ROWS)
    try:
        nodes[0].status = "resolved"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CausalNode は frozen であるべき")


def test_duplicate_ids_are_collapsed():
    nodes = build_dag(ROWS + [dict(ROWS[0], target_episode=99)])
    assert len(nodes) == 3
    assert next(n for n in nodes if n.foreshadowing_id == 1).target_episode == 99


def test_empty_description_produces_no_edge():
    assert edges_of([dict(ROWS[0], description="")]) == []


def test_empty_input_is_safe():
    assert build_dag([]) == [] and edges_of([]) == []


def test_unknown_status_is_normalised():
    assert build_dag([dict(ROWS[0], status="weird")])[0].status == "unknown"


def test_edges_follow_continuation_markers():
    chain = _chain(3)
    assert [(e.before, e.after) for e in edges_of(chain)] == [(1, 2), (2, 3)]


def test_terminal_node_is_not_used_as_predecessor():
    rows = [
        {"id": 1, "status": "resolved", "description": "回収済み"},
        {"id": 2, "status": "planted", "description": "後続の結果"},
    ]
    assert edges_of(rows) == []


def test_malformed_rows_are_skipped():
    nodes = build_dag([{"target_episode": 3}, "not-a-dict", {"id": "x"}, {"id": 5}])
    assert [n.foreshadowing_id for n in nodes] == [5]


# ── Step 6: 位相順序と依存伝播 ────────────────────────────────────
def test_topological_order_is_a_permutation():
    order = topological_order(_chain(20))
    assert sorted(order) == list(range(1, 21))


def test_topological_order_respects_edges():
    order = topological_order(_chain(5))
    assert order.index(1) < order.index(2) < order.index(5)


def test_cycle_does_not_hang():
    rows = [
        {"id": 1, "target_episode": 2, "status": "planted", "description": "後続の結果"},
        {"id": 2, "target_episode": 3, "status": "planted", "description": "後続の結果"},
    ]
    order = topological_order(rows)
    assert sorted(order) == [1, 2]


def test_self_loop_is_safe():
    rows = [{"id": 1, "target_episode": 2, "status": "planted", "description": "後続の結果"}]
    assert topological_order(rows) == [1]


def test_dependents_are_transitive():
    rows = _chain(4)
    assert dependents_of(rows, 1) == [2, 3, 4]
    assert dependents_of(rows, 4) == []


def test_roots_are_in_degree_zero():
    rows = _chain(4)
    assert roots_of(rows) == [1]


def test_isolated_node_is_a_root():
    rows = _chain(2) + [{"id": 9, "status": "planted", "description": "独立した伏線"}]
    assert roots_of(rows) == [1, 9]


def test_large_input_does_not_recurse():
    order = topological_order(_chain(10000))
    assert len(order) == 10000


def test_invalid_dependents_returns_empty():
    assert dependents_of(_chain(3), 999) == []
    assert dependents_of(_chain(3), "x") == []


def test_node_dataclass_is_plain_data():
    node = CausalNode(foreshadowing_id=1, target_episode=None, status="planted")
    assert node.target_episode is None
