"""T6: QueryComposer 単体テスト (Plan R5 C6 / T6).

決定論性・キーワード上限・空プロット耐性を検証。LLM 不使用。
"""

from __future__ import annotations

from src.integrations.rag.query_composer import QueryComposer


def test_deterministic_same_input_same_output() -> None:
    qc = QueryComposer()
    kw = dict(
        plot_summary="アルカディアの古代魔法は王都で使われた。",
        scenes=["シーンA: 開幕", "シーンB: 衝突"],
        character_names=["アルト", "アリス"],
        previous_tail="前話末尾の引き。",
        foreshadowing_keywords=["禁忌魔法"],
    )
    r1 = qc.compose_episode_query(**kw)
    r2 = qc.compose_episode_query(**kw)
    assert r1 == r2, "決定論的でない"
    assert "アルカディア" in r1["query"]
    assert len(r1["keywords"]) <= 8
    assert "禁忌魔法" in r1["keywords"]


def test_empty_plot_returns_something() -> None:
    qc = QueryComposer()
    r = qc.compose_episode_query()
    assert isinstance(r["query"], str) and r["query"]
    assert isinstance(r["keywords"], list)


def test_keywords_capped_and_stopwords_removed() -> None:
    qc = QueryComposer()
    r = qc.compose_episode_query(
        plot_summary=" " + "、".join(["言葉"] * 40),
        scenes=[],
        character_names=[],
        previous_tail="",
    )
    assert len(r["keywords"]) <= 8
    assert "は" not in r["keywords"]
    assert "を" not in r["keywords"]
