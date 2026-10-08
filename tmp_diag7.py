import asyncio
from tests.e2e.test_regeneration_loop_e2e import LowQualityMockLLM
from src.services.audit_aggregator import AuditAggregator
from src.agents.specialists.adapter import load_audit_weights
from src.agents.specialists import (
    ConsistencyAuditor, CreativityAuditor, ReaderHookAuditor, EmotionCurveAuditor,
    StyleAuditor, FactualAuditor, StructureAuditor, MultimodalAuditor,
)


async def main():
    low_llm = LowQualityMockLLM()
    specs = [
        ConsistencyAuditor(llm=low_llm), CreativityAuditor(llm=low_llm),
        ReaderHookAuditor(llm=low_llm), EmotionCurveAuditor(llm=low_llm),
        StyleAuditor(llm=low_llm), FactualAuditor(llm=low_llm),
        StructureAuditor(llm=low_llm), MultimodalAuditor(llm=low_llm),
    ]
    weights = load_audit_weights()
    print("weights:", weights)
    agg = AuditAggregator(specialists=specs, weights=weights, calibrator=None)
    ctx = {
        "draft_text": "昨日の戦いで死んだはずの仲間が朝ごはんを食べていた。今日はいい天気だ。",
        "world_bible": {"characters": {"仲間": {"alive": False, "status": "deceased"}}},
        "illustration_prompt": "朝食を食べる仲間たち",
    }
    await agg.run_all(ctx)
    res = agg.aggregate()
    print("by_specialist:", res.by_specialist)
    print("calibrated:", res.calibrated_by_specialist)
    print("lowest:", res.lowest_dimension())


asyncio.run(main())
