"""関連度スコアリングの回帰テスト（PLAN_W5 Step 9 / ネットワークを一切使わない）。"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.services.foreshadowing.relevance import cosine, score_and_select  # noqa: E402

CANDS = [
    {"id": 1, "title": "古代の魔導書", "description": "迷宮で拾った古い巻物", "planted_episode": 2},
    {"id": 2, "title": "幼馴染の約束", "description": "町の広場で交わした言葉", "planted_episode": 3},
]


def test_cosine_basics():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_jaccard_fallback_ranks_relevant_first():
    out = score_and_select("古代の魔導書を読み解く", CANDS, top_k=1)
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_input_is_not_mutated():
    before = [dict(c) for c in CANDS]
    score_and_select("魔導書", CANDS, top_k=2)
    assert CANDS == before


def test_zero_top_k_returns_empty():
    assert score_and_select("魔導書", CANDS, top_k=0) == []
    assert score_and_select("魔導書", CANDS, top_k=-1) == []


def test_overdue_gets_boost():
    out = score_and_select("魔導書", [dict(CANDS[0], target_episode=1)], top_k=1, current_episode=20)
    assert out and out[0]["relevance"] >= 1.0


def test_failing_embedding_falls_back():
    def boom(text):
        raise RuntimeError("no api")

    out = score_and_select("古代の魔導書", CANDS, top_k=2, embedding_fn=boom)
    assert len(out) == 2
    assert out[0]["id"] == 1


def test_embedding_fn_is_used_when_available():
    def embed(text):
        # 「古代の魔導書」を含む文だけが 1 方向に強い
        return [1.0, 0.0] if "魔導書" in text else [0.0, 1.0]

    out = score_and_select("古代の魔導書を読み解く", CANDS, top_k=2, embedding_fn=embed)
    assert [c["id"] for c in out] == [1, 2]
    assert out[0]["relevance"] > out[1]["relevance"]


def test_relevance_key_is_added():
    out = score_and_select("魔導書", CANDS, top_k=2)
    assert all("relevance" in c for c in out)


def test_empty_candidates_is_safe():
    assert score_and_select("魔導書", [], top_k=2) == []


def test_non_dict_candidates_are_skipped():
    out = score_and_select("魔導書", ["nope", dict(CANDS[0])], top_k=2)
    assert [c["id"] for c in out] == [1]
