"""伏線の因果DAG（Narrative Causal DAG）（PLAN_W5_CAUSAL_FORESIGHT_12STEPS Step 5-6）。

## なぜ要るのか（W5-03）

伏線_python には **依存関係という概念が存在しない**。
`ForeshadowingModel` も `Foreshadowing` 旧モデルも `depends_on` 相当を持たない。
物語論的には「B の回収には A の回収（または A の進展）が必要」という因果順序が要る。

`ForeshadowingRescheduler` が A を第30話へ延期しても、
**A を前提とする B は第12話のまま放置される**（＝因果矛盾）が現在起きうる。

## 依存推定は完全に決定論的

行の並び順（`id` 昇順）で、`description` に「〜に続く」「〜の結果」「〜の顛末」
等の **後続を示す語** が含まれるとき、直前の**未解決ノード**へ辺を張る。
**LLM は呼ばない**（LLM を足すのは本計画のスコープ外。別計画で扱う）。

- I/O ゼロ・LLM ゼロ・stdlib のみ
- 例外を送出しない（不正入力は空リスト / 空グラフ）
- 再帰を使わない（`sys.setrecursionlimit` に依存しない）
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

#: `status` として受理する来歴。未知値は `UNKNOWN_STATUS` に丸める。
KNOWN_STATUSES = ("planted", "progressed", "resolved", "abandoned")

#: 未知の来歴の丸め先。
UNKNOWN_STATUS = "unknown"

#: 終端状態（もう他と因果関係を持たない）。
_TERMINAL_STATUSES = ("resolved", "abandoned")

#: 「この伏線は前の伏線に続く」を示す語。**後続の依存を張るトリガ**。
_CONTINUATION_MARKERS = ("に続く", "の結果", "の顛末", "後続")


@dataclass(frozen=True)
class CausalNode:
    """因果DAGの1ノード（伏線1本に対応）。"""

    foreshadowing_id: int
    target_episode: Optional[int]
    status: str


@dataclass(frozen=True)
class CausalEdge:
    """`before` が `after` の前提であること。"""

    before: int
    after: int


def _normalise_rows(rows: Any) -> list[dict]:
    """id 昇順・**後勝ち**で1本に畳んだ行のリストを返す（純関数・例外を送出しない）。"""
    if not rows:
        return []
    merged: dict[int, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            fid = int(row.get("id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        merged[fid] = row
    return [merged[k] for k in sorted(merged)]


def _status_of(row: dict) -> str:
    """来歴を正規化する（未知値は `"unknown"` に丸める）。"""
    raw = str(row.get("status") or "").strip().lower()
    return raw if raw in KNOWN_STATUSES else UNKNOWN_STATUS


def _target_of(row: dict) -> Optional[int]:
    target = row.get("target_episode")
    if isinstance(target, bool):
        return None
    return target if isinstance(target, int) else None


def build_dag(rows: list[dict]) -> list[CausalNode]:
    """伏線行から因果DAGのノード列を作る（辺は不要なら `edges_of` を使う）。

    Args:
        rows: `{"id", "target_episode", "status", "description"}` のリスト

    Returns:
        `CausalNode` のリスト（id 昇順）。不正行は落とす。
    """
    return [
        CausalNode(
            foreshadowing_id=int(row["id"]),
            target_episode=_target_of(row),
            status=_status_of(row),
        )
        for row in _normalise_rows(rows)
    ]


def edges_of(rows: list[dict]) -> list[CausalEdge]:
    """依存辺を返す（`before` → `after`、id 昇順）。

    `description` が空文字の行は **必ず辺を張らない**（cycle 防止）。
    """
    ordered = _normalise_rows(rows)
    edges: list[CausalEdge] = []
    prev_id: Optional[int] = None  # 直前の「未解決」ノード
    for row in ordered:
        fid = int(row["id"])
        description = str(row.get("description") or "")
        has_marker = bool(description.strip()) and any(
            marker in description for marker in _CONTINUATION_MARKERS
        )
        if has_marker and prev_id is not None:
            edges.append(CausalEdge(before=prev_id, after=fid))
        if _status_of(row) not in _TERMINAL_STATUSES:
            prev_id = fid
    return edges


def _adjacency(rows: list[dict]) -> tuple[list[int], dict[int, set[int]]]:
    """`(id 昇順のノード, 隣接表)` を返す（自己ループは除去する）。"""
    ordered = [int(r["id"]) for r in _normalise_rows(rows)]
    adj: dict[int, set[int]] = {i: set() for i in ordered}
    for edge in edges_of(rows):
        if edge.before == edge.after:
            continue
        if edge.before in adj and edge.after in adj:
            adj[edge.before].add(edge.after)
    return ordered, adj


def _in_degrees(adj: dict[int, set[int]]) -> dict[int, int]:
    indeg: dict[int, int] = {node: 0 for node in adj}
    for targets in adj.values():
        for nxt in targets:
            indeg[nxt] += 1
    return indeg


def roots_of(rows: list[dict]) -> list[int]:
    """入次数 0 のノード id（id 昇順）。"""
    ordered, adj = _adjacency(rows)
    indeg = _in_degrees(adj)
    return [i for i in ordered if indeg[i] == 0]


def topological_order(rows: list[dict]) -> list[int]:
    """Kahn 法による位相順序。**必ず全IDをちょうど1回ずつ**返す。

    閉路があっても無限ループしない。閉路のために消費できなかったノードは
    **id 昇順で後ろに足す**（＝脱落も重複も無い）。再帰は使わない。
    """
    ordered, adj = _adjacency(rows)
    indeg = _in_degrees(adj)

    queue = deque(i for i in ordered if indeg[i] == 0)
    out: list[int] = []
    while queue:
        node = queue.popleft()
        out.append(node)
        for nxt in sorted(adj[node]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)

    if len(out) == len(ordered):
        return out
    seen = set(out)
    return out + [i for i in ordered if i not in seen]


def dependents_of(rows: list[dict], foreshadowing_id: int) -> list[int]:
    """`foreshadowing_id` に依存する伏線（直接 + 推移閉包）を id 昇順で返す。

    依存の向きは「前提 → 結果」。よって `1 → 2 → 3` のとき
    `dependents_of(rows, 1) == [2, 3]`。
    """
    ordered, adj = _adjacency(rows)
    try:
        start = int(foreshadowing_id)
    except (TypeError, ValueError):
        return []
    if start not in adj:
        return []

    seen = {start}
    stack = [start]
    found: set[int] = set()
    while stack:
        node = stack.pop()
        for nxt in adj[node]:
            if nxt not in seen:
                seen.add(nxt)
                found.add(nxt)
                stack.append(nxt)
    return [i for i in ordered if i in found]
