"""services/spine_resolver.py — 構造テンプレート層の解決エンジン（LLM 0回・決定論）。

親提案 §4。設計上の拘束:
- **LLM を一度も呼ばない**。同じ入力は必ず同じ出力。
- **相対位置で構造を表す**。`total_eps` を変えても構造は破綻しない。
- **圧縮モード**で 1 話短編にも構造が入る（発端・中点反転・クライマックスは消さない）。

計算量は beat 数（<=34）だけに比例し、話数には比例しない。
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace

from config.story_spine.beat import BEAT_VOCABULARY, BeatInstance, Spine
from config.story_spine.loader import get_length, get_pattern

logger = logging.getLogger(__name__)

# 圧縮時に「この2つの beat を1つにまとめてよい」グループ。
# 先頭要素が展開後の代表キー。
_MERGE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("inciting", "cold_open", "revelation", "humiliation"),
    ("failure", "all_is_lost"),
    ("dark_night", "betrayal"),
    ("turn_of_tide", "decision"),
    ("last_stand", "final_choice", "truth_reveal"),
    ("aftermath", "payoff", "residue"),
    ("volume_hook", "coda"),
    ("expansion", "stream_reaction", "training"),
    ("deepening", "comic_relief", "interlude", "promise"),
    ("rising_tension", "stakes_raise", "foreshadow", "gossip", "daily_loop"),
)

# 圧縮しても決して消さない 3 つ（親提案 §4.3 の不変条件）
_ALWAYS_KEEP = ("midpoint_reversal", "climax")

# 1話構成でも残る最小 beat 数。beat 数 > 話数のときは重なりを許容する。
_MIN_SURVIVORS = 3

# 最初に必ず残すフック beat の候補
_HOOK_KEYS = ("inciting", "humiliation", "cold_open", "revelation")


def _group_rep(key: str) -> str | None:
    for group in _MERGE_GROUPS:
        if key in group:
            return group[0]
    return None


def _merge_duty(a: str, b: str) -> str:
    """結合した beat の duty。60字以内に収める（語彙の約束）。"""
    head = a.rstrip("。")
    merged = f"{head}、続けて{b.rstrip('。')}。"
    return merged[:59] + "。" if len(merged) > 60 else merged


class _Node:
    """圧縮途中の beat。span を保持し、最終的に BeatInstance になる。"""

    __slots__ = ("key", "span", "members")

    def __init__(self, key: str, span: tuple[float, float], members: tuple[str, ...] = ()) -> None:
        self.key = key
        self.span = span
        self.members = members or (key,)


def _nodes(pattern: dict, market_key: str, eps: int) -> list[_Node]:
    """パターンの beat 列を市場ルールで除してから _Node 列にする。"""
    raw = list(pattern.get("beats", []))
    nodes: list[_Node] = []
    for b in raw:
        key = b["key"]
        # Web 以外は「次の引き」を強制しない（一般文芸・単発に次はない）
        if key == "volume_hook" and market_key != "web":
            continue
        # 1話構成に両方収まらないので、Web でも話数が1なら落とす
        if key == "volume_hook" and eps < 2:
            continue
        # 幕間は連続構成では削る（情報量の増設より構成の明確さを優先）
        if key == "interlude" and eps < 3:
            continue
        nodes.append(_Node(key, tuple(b["span"])))
    return nodes


def _merge_span(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0], max(a[1], b[1]))


def _merge_pair(a: _Node, b: _Node) -> _Node:
    rep = _group_rep(a.key) or a.key
    return _Node(rep, _merge_span(a.span, b.span), a.members + b.members)


def _is_mandatory(node: _Node, index: int, total: int) -> bool:
    if node.key in _ALWAYS_KEEP:
        return True
    return index == 0 or index == total - 1


def _compress(nodes: list[_Node], eps: int) -> list[_Node]:
    """len(nodes) > eps の間、隣接 beat を併合する。3不変条件は保つ。

    話数が beat 数より少ない場合（例: 1話短編）は、話数まで削らず
    `_MIN_SURVIVORS` で止める。残った beat は同じ話に重なる。
    """
    nodes = list(nodes)
    target = max(eps, _MIN_SURVIVORS)
    while len(nodes) > target:
        merged_any = False
        # 1) マージグループ内の隣接ペアを優先的に併合
        for i in range(len(nodes) - 1):
            if _is_mandatory(nodes[i], i, len(nodes)) or _is_mandatory(nodes[i + 1], i + 1, len(nodes)):
                continue
            ra, rb = _group_rep(nodes[i].key), _group_rep(nodes[i + 1].key)
            if ra is not None and ra == rb:
                nodes[i : i + 2] = [_merge_pair(nodes[i], nodes[i + 1])]
                merged_any = True
                break
        if merged_any:
            continue
        # 2) それでも多い場合は、任意保護されていない隣接ペアを併合
        for i in range(len(nodes) - 1):
            if _is_mandatory(nodes[i + 1], i + 1, len(nodes)):
                continue
            nodes[i : i + 2] = [_merge_pair(nodes[i], nodes[i + 1])]
            merged_any = True
            break
        if not merged_any:
            # 3) 最後にひとつだけ、_ALWAYS_KEEP 以外を隣接 beat へ吸収させる
            for i in range(len(nodes) - 1):
                if nodes[i + 1].key in _ALWAYS_KEEP:
                    continue
                nodes[i : i + 2] = [_merge_pair(nodes[i], nodes[i + 1])]
                merged_any = True
                break
        if not merged_any:
            # 4) これ以上は削れない。このまま返す（例外は投げない）
            logger.warning("圧縮しきれず %d beats / %d eps のまま", len(nodes), eps)
            break
    return nodes


def _cumulative_bounds(nodes: list[_Node]) -> list[float]:
    n = len(nodes)
    widths = [max(b[1] - b[0], 1e-6) for b in (nd.span for nd in nodes)]
    total = sum(widths)
    bounds = [0.0]
    acc = 0.0
    for w in widths:
        acc += w / total
        bounds.append(acc)
    bounds[0] = 0.0
    bounds[-1] = 1.0
    for i in range(1, n):
        bounds[i] = min(max(bounds[i], bounds[i - 1]), 1.0)
    return bounds


def _to_instances(nodes: list[_Node], eps: int) -> list[BeatInstance]:
    """相対位置を話数区間に量子化する。1..eps を隙なく埋めることを保証する。"""
    bounds = _cumulative_bounds(nodes)
    spans: list[tuple[int, int, _Node]] = []
    for i, node in enumerate(nodes):
        s = int(math.floor(bounds[i] * eps)) + 1
        e = int(math.floor(bounds[i + 1] * eps))
        s = max(1, min(s, eps))
        e = max(1, min(e, eps))
        if e < s:
            e = s
        spans.append((s, e, node))

    # 1话目から始める
    spans[0] = (1, spans[0][1], spans[0][2])
    if len(spans) > eps:
        # beat が話数より多い（例: 1話短編）。重なりを許容し、全話に割り当てる。
        spans = [(1, eps, node) for _, _, node in spans]
        return _build(spans)
    # 隙間と重なりを潰す
    for i in range(1, len(spans)):
        prev_end = spans[i - 1][1]
        s, e, node = spans[i]
        if s <= prev_end:
            s = prev_end + 1
        if e < s:
            e = s
        spans[i] = (min(s, eps), min(e, eps), node)
    for i in range(len(spans) - 1):
        if spans[i][1] >= spans[i + 1][0]:
            spans[i] = (spans[i][0], spans[i + 1][0] - 1, spans[i][2])
    # 削られたノードを除去して、1..eps を確実に被覆させる
    spans = [sp for sp in spans if sp[0] <= sp[1]]
    spans[0] = (1, spans[0][1], spans[0][2])
    spans[-1] = (spans[-1][0], eps, spans[-1][2])
    for i in range(1, len(spans)):
        if spans[i][0] <= spans[i - 1][1]:
            spans[i] = (spans[i - 1][1] + 1, spans[i][1], spans[i][2])
    spans = [sp for sp in spans if sp[0] <= sp[1]]
    if not spans:
        spans = [(1, eps, nodes[0])]

    return _build(spans)


def _build(spans: list[tuple[int, int, _Node]]) -> list[BeatInstance]:
    """(ep_start, ep_end, node) 列を BeatInstance 列に変換する。"""
    out: list[BeatInstance] = []
    for s, e, node in spans:
        primary = BEAT_VOCABULARY[node.key]
        duty = primary.duty
        for extra in node.members[1:]:
            duty = _merge_duty(duty, BEAT_VOCABULARY[extra].duty)
        out.append(
            BeatInstance(
                ep_start=s,
                ep_end=e,
                key=node.key,
                label=primary.label,
                role=primary.role,
                duty=duty,
                tension=primary.tension,
                artifact=primary.artifact,
            )
        )
    return out


def _as(inst: BeatInstance, beat) -> BeatInstance:
    """既存 instance の役割だけを、指定した語彙の beat へ差し替える（話数は保持）。"""
    return BeatInstance(
        inst.ep_start, inst.ep_end, beat.key, beat.label, beat.role,
        beat.duty, beat.tension, beat.artifact,
    )


def _enforce_invariants(
    instances: list[BeatInstance], market_key: str, eps: int
) -> list[BeatInstance]:
    """3不変条件を強制する。1 話でも 発端 → 中点反転 → クライマックス を保つ。"""
    if not instances:
        return instances
    climax_def = BEAT_VOCABULARY["climax"]
    mid_def = BEAT_VOCABULARY["midpoint_reversal"]
    hook_def = BEAT_VOCABULARY["volume_hook"]

    keys = [i.key for i in instances]

    if "climax" not in keys:
        tail = instances[-1]
        instances[-1] = _as(tail, climax_def)
    if "midpoint_reversal" not in keys and len(instances) >= 3:
        idx = len(instances) // 2
        instances[idx] = _as(instances[idx], mid_def)
    if market_key == "web" and eps >= 2 and instances[-1].key != "volume_hook":
        # Web 連載は話末の引きで終わる。最終話 (ep == eps) を volume_hook に譲る。
        last = instances[-1]
        hook = BeatInstance(
            eps, eps, hook_def.key, hook_def.label,
            hook_def.role, hook_def.duty, hook_def.tension, hook_def.artifact,
        )
        if last.ep_end > last.ep_start:
            # 末尾 beat が複数話なら詰めてから hook を足す
            instances[-1] = replace(last, ep_end=eps - 1)
            instances.append(hook)
        else:
            # 末尾 beat が最終話1話だけなら、重要でない 1 話 beat を削って hook に譲る。
            while (
                len(instances) > 1
                and instances[-1].key not in _ALWAYS_KEEP
                and instances[-1].ep_start >= instances[-1].ep_end
                and instances[-1].ep_end >= eps
            ):
                instances.pop()
            tail = instances[-1]
            if tail.ep_start >= eps:
                return instances  # 譲れる余地がない
            instances[-1] = replace(tail, ep_end=eps - 1)
            instances.append(hook)
    return instances


def resolve_spine(
    pattern_key: str,
    length_key: str,
    market_key: str,
    total_eps: int | None = None,
) -> Spine:
    """構造テンプレートを 1 作品分の Spine に展開する。**LLM を呼ばない。**"""
    pattern = get_pattern(pattern_key) or {}
    length = get_length(length_key) or {}

    eps_range = length.get("eps_range", [1, 1])
    if total_eps is None:
        total_eps = (int(eps_range[0]) + int(eps_range[1])) // 2
    eps = max(1, int(total_eps))

    nodes = _nodes(pattern, market_key, eps)
    if not nodes:
        logger.warning("パターン %r に beats が無い。空の Spine を返す。", pattern_key)
        return Spine(pattern=pattern_key, length=length_key, market=market_key, total_eps=eps)

    if len(nodes) > eps:
        nodes = _compress(nodes, eps)
    instances = _to_instances(nodes, eps)
    instances = _enforce_invariants(instances, market_key, eps)

    return Spine(
        pattern=pattern_key,
        length=length_key,
        market=market_key,
        total_eps=eps,
        beats=instances,
    )


__all__ = ["resolve_spine"]
