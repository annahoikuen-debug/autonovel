"""src/agents/diversity_scorer.py と src/agents/debate.py の単体テスト."""

from __future__ import annotations

from src.agents.debate import NullDebateAgent
from src.agents.diversity_scorer import DiversityScorer


async def test_diversity_score():
    scorer = DiversityScorer()
    res = await scorer.score("a b a c")
    assert res == {"diversity": 0.75, "word_count": 4, "unique_words": 3}


async def test_diversity_score_empty():
    scorer = DiversityScorer()
    res = await scorer.score("")
    assert res == {"diversity": 0.0, "word_count": 0, "unique_words": 0}


async def test_diversity_scorer_run():
    scorer = DiversityScorer()
    res = await scorer.run(content="x y")
    assert res["word_count"] == 2
    res2 = await scorer.run()
    assert res2["word_count"] == 0


async def test_null_debate_agent():
    agent = NullDebateAgent()
    concept = {"a": 1}
    res = await agent.run_debate(concept, rounds=3)
    assert res == {"final_concept": concept, "debate_log": []}
    assert res["final_concept"] is concept
