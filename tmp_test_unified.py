import asyncio
from src.agents.specialists.unified_auditor import UnifiedAuditor

class LowQualityMockLLM:
    async def generate(self, prompt: str, temperature: float = 0.2) -> str:
        print(f"=== UNIFIED AUDITOR PROMPT (first 500 chars) ===")
        print(prompt[:500])
        print()
        # Return JSON with character_consistency being the lowest
        return '{"hook_score": 52.0, "emotional_score": 58.0, "character_consistency": 45.0, "overall_score": 55.0, "critique": "test", "actionable_patch": null}'
    
    async def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        return await self.generate(prompt, temperature)

async def test():
    unified = UnifiedAuditor(llm_gateway=LowQualityMockLLM())
    
    # Test audit_quantitative
    text = "昨日の戦いで死んだはずの仲間が朝ごはんを食べていた。今日はいい天気だ。"
    quant_score, quant_meta = unified.audit_quantitative(text)
    print(f"Quantitative score: {quant_score}")
    print(f"Quantitative meta: {quant_meta}")
    
    # Test audit_qualitative
    qual = await unified.audit_qualitative(text)
    print(f"Qualitative: hook={qual.hook_score}, emotional={qual.emotional_score}, character_consistency={qual.character_consistency}, overall={qual.overall_score}")
    
    # Test full audit
    report = await unified.audit(text)
    print(f"Final report: final_score={report.final_score}, quantitative_score={report.quantitative_score}")
    print(f"  qualitative: hook={report.qualitative.hook_score}, emotional={report.qualitative.emotional_score}, character_consistency={report.qualitative.character_consistency}, overall={report.qualitative.overall_score}")

asyncio.run(test())