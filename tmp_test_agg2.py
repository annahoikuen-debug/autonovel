import asyncio
from src.agents.orchestrator import AgentContext, AgentName
from src.agents.specialists.adapter import AuditAggregatorNode, load_audit_weights
from src.services.audit_aggregator import AuditAggregator
from src.agents.specialists import (
    ConsistencyAuditor,
    CreativityAuditor,
    ReaderHookAuditor,
    EmotionCurveAuditor,
    StyleAuditor,
    FactualAuditor,
    StructureAuditor,
    MultimodalAuditor,
)


class LowQualityMockLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        print(f"=== UNIFIED AUDITOR PROMPT (first 300 chars) ===")
        print(prompt[:300])
        print()
        # Return JSON with character_consistency being the lowest
        return '{"hook_score": 52.0, "emotional_score": 58.0, "character_consistency": 45.0, "overall_score": 55.0, "critique": "test", "actionable_patch": null}'
    
    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return await self.generate(prompt, temperature)


async def test():
    weights = load_audit_weights()

    low_llm = LowQualityMockLLM()
    specialists_round1 = [
        ConsistencyAuditor(llm=low_llm),
        CreativityAuditor(llm=low_llm),
        ReaderHookAuditor(llm=low_llm),
        EmotionCurveAuditor(llm=low_llm),
        StyleAuditor(llm=low_llm),
        FactualAuditor(llm=low_llm),
        StructureAuditor(llm=low_llm),
        MultimodalAuditor(llm=low_llm),
    ]
    aggregator1 = AuditAggregator(specialists=specialists_round1, weights=weights)
    # Pass llm to node so UnifiedAuditor uses our mock
    node1 = AuditAggregatorNode(aggregator=aggregator1, llm=low_llm)

    ctx = AgentContext(
        book_id=10,
        branch_id=1,
        ep_num=1,
        artifacts={
            "drafted_text": "昨日の戦いで死んだはずの仲間が朝ごはんを食べていた。今日はいい天気だ。",
            "world_bible": {"characters": {"仲間": {"alive": False, "status": "deceased"}}},
            "illustration_prompt": "朝食を食べる仲間たち",
        },
    )

    res1 = await node1.execute(ctx)

    print("\n=== RESULTS ===")
    print(f"audit_score: {res1.artifacts.get('audit_score')}")
    print(f"specialist_scores: {res1.artifacts.get('specialist_scores')}")
    print(f"lowest_dimension: {res1.artifacts.get('lowest_dimension')}")
    print(f"should_retry: {res1.should_retry}")
    print(f"next_agent: {res1.next_agent}")
    print(f"regeneration_directive: {res1.artifacts.get('regeneration_directive')}")


asyncio.run(test())