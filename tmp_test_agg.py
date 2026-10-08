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
    """Returns low scores for draft with contradictions and weak hooks."""

    async def ainvoke(self, prompt: str, **kwargs):
        class Resp:
            def __init__(self, content):
                self.content = content

        text = str(prompt)
        print(f"\n=== MOCK RECEIVED PROMPT (first 200 chars) ===")
        print(text[:200])
        print(f"=== KEYWORDS ===")
        for kw in ["Consistency", "矛盾", "死亡キャラクター", "論理破綻", "再登場", "Reader Hook", "引き", "Creativity", "Emotion", "Style", "Factual", "Structure", "Multimodal"]:
            if kw in text:
                print(f"  FOUND: {kw}")
        
        if "Consistency" in text or "矛盾" in text or "死亡キャラクター" in text or "論理破綻" in text or "再登場" in text:
            content = '{"score": 45.0, "critique": "死んだはずの仲間が説明なしに現れており重大な論理矛盾があります。", "suggestions": ["死亡キャラの登場理由を修正するか別キャラに置換"], "confidence": 0.85, "reasoning": "死亡キャラの生存描写と設定の直接矛盾"}'
            print("  -> MATCHED: consistency")
        elif "Reader Hook" in text or "引き" in text:
            content = '{"score": 52.0, "critique": "冒頭に引きがなく、結末も平坦でクリフハンガーがありません。", "suggestions": ["末尾に謎を提示"], "confidence": 0.85, "reasoning": "冒頭フックとクリフハンガーが欠如"}'
            print("  -> MATCHED: reader_hook")
        elif "Creativity" in text or "独創" in text or "独自" in text:
            content = '{"score": 55.0, "critique": "独創性が不足しています。", "suggestions": ["新しい視点を追加"], "confidence": 0.8, "reasoning": "テンプレート的な展開"}'
            print("  -> MATCHED: creativity")
        elif "Emotion" in text or "感情" in text or "情緒" in text:
            content = '{"score": 58.0, "critique": "感情描写が平坦です。", "suggestions": ["心理描写を深める"], "confidence": 0.8, "reasoning": "感情の振れ幅が小さい"}'
            print("  -> MATCHED: emotion_curve")
        elif "Style" in text or "文体" in text or "スタイル" in text:
            content = '{"score": 59.0, "critique": "文体に改善の余地があります。", "suggestions": ["リズムを整える"], "confidence": 0.8, "reasoning": "文末が単調"}'
            print("  -> MATCHED: style")
        elif "Factual" in text or "事実" in text or "考証" in text:
            content = '{"score": 57.0, "critique": "考証に不備があります。", "suggestions": ["専門知識を確認"], "confidence": 0.8, "reasoning": "事実関係に誤り"}'
            print("  -> MATCHED: factual")
        elif "Structure" in text or "構成" in text or "起承転結" in text:
            content = '{"score": 56.0, "critique": "構成に問題があります。", "suggestions": ["起承転結を明確に"], "confidence": 0.8, "reasoning": "中だるみしている"}'
            print("  -> MATCHED: structure")
        elif "Multimodal" in text or "マルチモーダル" in text or "視覚" in text:
            content = '{"score": 60.0, "critique": "マルチモーダル要素が不足。", "suggestions": ["視覚描写を追加"], "confidence": 0.8, "reasoning": "テキストのみ"}'
            print("  -> MATCHED: multimodal")
        else:
            content = '{"score": 60.0, "critique": "平均以下の品質です。", "suggestions": ["表現の推敲"], "confidence": 0.8, "reasoning": "総合的に品質が低い"}'
            print("  -> MATCHED: default")

        return Resp(content)


async def test():
    weights = load_audit_weights()

    low_llm = LowQualityMockLLM()
    specialists = [
        ConsistencyAuditor(llm=low_llm),
        CreativityAuditor(llm=low_llm),
        ReaderHookAuditor(llm=low_llm),
        EmotionCurveAuditor(llm=low_llm),
        StyleAuditor(llm=low_llm),
        FactualAuditor(llm=low_llm),
        StructureAuditor(llm=low_llm),
        MultimodalAuditor(llm=low_llm),
    ]
    aggregator = AuditAggregator(specialists=specialists, weights=weights)
    node = AuditAggregatorNode(aggregator=aggregator)

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

    res = await node.execute(ctx)

    print("\n=== RESULTS ===")
    print(f"audit_score: {res.artifacts.get('audit_score')}")
    print(f"specialist_scores: {res.artifacts.get('specialist_scores')}")
    print(f"lowest_dimension: {res.artifacts.get('lowest_dimension')}")
    print(f"should_retry: {res.should_retry}")
    print(f"next_agent: {res.next_agent}")


asyncio.run(test())