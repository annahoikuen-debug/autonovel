"""伏線とシーンの関連度スコアリング（PLAN_W5_CAUSAL_FORESIGHT_12STEPS Step 9 / W5-02）。

## なぜ要るのか

`prompts/manager._select_background_foreshadowings` のソートキーは
「期限超過 → 設置話の新しい順」だけで、**そのシーンとの関連度を一切見ていない**。
結果として **似ていない伏線も同じプロンプトに注入**される。

## 制約

- **ネットワークを直接叩かない。** `EmbeddingService` は **DI 引数**（`embedding_fn`）で受ける。
- `embedding_fn` が `None` のときは **文字一致（Jaccard）** で代用する
  → Embedding API を一切呼ばずに動く＝**API コストゼロ**／テストが軽い。
- `embedding_fn` が例外を投げた場合も **Jaccard にフォールバック**（例外は送出しない）。
- `flags` は参照しない（`top_k` の既定は呼び出し側が `flags.get_relevance_top_k()` を渡す）。
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

#: スコアの重み（関連度 0.7 / 減衰 0.3）。
RELEVANCE_WEIGHT = 0.7
DECAY_WEIGHT = 0.3

#: 減衰の分母に使う話数。
DECAY_SCALE = 10.0

#: 期限超過時の補正倍率。
_OVERDUE_BOOST = 1.1
#: 期限超過は最優先カテゴリなので、下限を 1.0 に底上げする（降順ソートで必ず先頭）。
_OVERDUE_FLOOR = 1.0
#: 期限超過でも際限なく Points を増やさないための上限。
_OVERDUE_CEILING = 1.5


def cosine(a: list[float], b: list[float]) -> float:
    """コサイン類似度（純関数）。**長さ不一致 / ゼロベクトルで 0.0**。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _jaccard(a: str, b: str) -> float:
    """文字集合の Jaccard 係数（純関数・ネットワーク不要）。"""
    set_a, set_b = set(a or ""), set(b or "")
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def _text_of(candidate: dict) -> str:
    return f"{candidate.get('title', '')}{candidate.get('description', '')}"


def _decay(candidate: dict, current_episode: Optional[int]) -> float:
    """設置の話数からの経過による減衰（1.0 → 0.0 へ単調減少）。"""
    if current_episode is None:
        return 1.0
    planted = candidate.get("planted_episode")
    if not isinstance(planted, int):
        return 1.0
    elapsed = max(0, current_episode - planted)
    return 1.0 / (1.0 + elapsed / DECAY_SCALE)


def _is_overdue(candidate: dict, current_episode: Optional[int]) -> bool:
    if current_episode is None:
        return False
    target = candidate.get("target_episode")
    return isinstance(target, int) and target < current_episode


def score_and_select(
    scene_text: str,
    candidates: list[dict],
    top_k: int = 2,
    embedding_fn: Optional[Callable[[str], Any]] = None,
    current_episode: Optional[int] = None,
) -> list[dict]:
    """シーンテキストと各候補の関連度でスコアリングし、上位 `top_k` 件を返す。

    Args:
        scene_text: 今のシーンを表すテキスト
        candidates: `{"id", "title", "description", "planted_episode", "target_episode"}`
        top_k: 返す上限件数（`0` 以下なら空リスト）
        embedding_fn: テキスト → ベクトルの関数。`None` / 例外時は Jaccard
        current_episode: 現在話数（減衰と期限超過判定に使う。`None` で無効化）

    Returns:
        **新しい dict のリスト**（入力は破壊しない）。各要素に `"relevance": float` を追加。
    """
    if not candidates or top_k <= 0:
        return []

    scene_vec: Optional[list[float]] = None
    if embedding_fn is not None:
        try:
            raw = embedding_fn(scene_text)
            if isinstance(raw, (list, tuple)):
                scene_vec = [float(x) for x in raw]
        except Exception:
            # Embedding が使えない／壊れている → Jaccard フォールバック
            scene_vec = None

    scored: list[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = _text_of(candidate)
        sim = _jaccard(scene_text, text)
        if scene_vec is not None:
            try:
                cand_vec = embedding_fn(text)  # type: ignore[misc]
                if isinstance(cand_vec, (list, tuple)):
                    sim = cosine(scene_vec, [float(x) for x in cand_vec])
            except Exception:
                sim = _jaccard(scene_text, text)
        score = RELEVANCE_WEIGHT * sim + DECAY_WEIGHT * _decay(candidate, current_episode)
        if _is_overdue(candidate, current_episode):
            score = min(_OVERDUE_CEILING, max(score * _OVERDUE_BOOST, _OVERDUE_FLOOR))
        item = dict(candidate)
        item["relevance"] = score
        scored.append(item)

    # 同点は id 昇順で決定的に並べる
    scored.sort(key=lambda c: (-c["relevance"], c.get("id") if c.get("id") is not None else 0))
    return scored[:top_k]
