"""Sensory Vocabulary Provider for Rhetoric and Sensory Expressions (Proposal 4)."""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
from src.mcp_servers.vocab_schemas import (
    SensoryWord,
    SampledVocabResult,
    parse_vocab_uri,
)


class SensoryVocabProvider:
    """ジャンル・情動強度ごとの感覚・レトリック語彙を管理し、オンデマンドサンプリングを提供するプロバイダー"""

    def __init__(self, auto_load_defaults: bool = True) -> None:
        self.vocab_sets: Dict[str, List[SensoryWord]] = {}
        if auto_load_defaults:
            self._init_builtin_vocab()

    def _init_builtin_vocab(self) -> None:
        """config.erotic_vocabulary からリッチな比喩・オノマトペ・心理語彙を初期ロード"""
        try:
            from config.erotic_vocabulary import (
                METAPHOR_BANK,
                ONOMATOPOEIA_BANK,
                PSYCHOLOGY_TEMPLATES,
                INTENSE_METAPHORS,
                INTENSE_ONOMATOPOEIA,
                INTENSE_PSYCHOLOGY,
            )

            erotic_words: List[SensoryWord] = []

            # 穏やか〜標準の比喩 (強度 0.3〜0.6)
            for m in METAPHOR_BANK:
                erotic_words.append(
                    SensoryWord(
                        word=m,
                        category="metaphor",
                        example_sentence=f"情動の描写: {m}",
                        intensity=0.5,
                        nuance="emotional_resonance",
                    )
                )

            # 極限・強度高の比喩 (強度 0.8〜1.0)
            for m in INTENSE_METAPHORS:
                erotic_words.append(
                    SensoryWord(
                        word=m,
                        category="metaphor",
                        example_sentence=f"極限の比喩: {m}",
                        intensity=0.9,
                        nuance="boundary_dissolution",
                    )
                )

            # オノマトペ・五感音 (強度 0.4〜0.9)
            for o in ONOMATOPOEIA_BANK:
                erotic_words.append(
                    SensoryWord(
                        word=o,
                        category="onomatopoeia",
                        example_sentence=f"微細な感覚音: {o}",
                        intensity=0.4,
                        nuance="sensory_texture",
                    )
                )
            for o in INTENSE_ONOMATOPOEIA:
                erotic_words.append(
                    SensoryWord(
                        word=o,
                        category="onomatopoeia",
                        example_sentence=f"激しい情動音: {o}",
                        intensity=0.85,
                        nuance="visceral_impact",
                    )
                )

            # 心理描写 (強度 0.4〜0.95)
            for p in PSYCHOLOGY_TEMPLATES:
                erotic_words.append(
                    SensoryWord(
                        word=p,
                        category="psychological",
                        example_sentence=f"心理の揺らぎ: {p}",
                        intensity=0.45,
                        nuance="internal_monologue",
                    )
                )
            for p in INTENSE_PSYCHOLOGY:
                erotic_words.append(
                    SensoryWord(
                        word=p,
                        category="psychological",
                        example_sentence=f"自制の崩壊と恍惚: {p}",
                        intensity=0.9,
                        nuance="loss_of_control",
                    )
                )

            self.register_words("erotic", erotic_words)
            self.register_words("romance", [w for w in erotic_words if w.intensity <= 0.7])
        except Exception as e:
            logger.warning("Failed to initialize builtin erotic vocabulary: %s", e)

    def register_words(self, genre: str, words: List[SensoryWord]) -> None:
        """指定ジャンルに感覚語彙リストを登録する"""
        if genre not in self.vocab_sets:
            self.vocab_sets[genre] = []
        self.vocab_sets[genre].extend(words)

    def sample_by_intensity(
        self,
        category: str = "all",
        intensity: float = 0.5,
        genre: str = "erotic",
        count: int = 4,
        seed: Optional[int] = None,
    ) -> SampledVocabResult:
        """指定の情動強度（0.0〜1.0）に近い語彙を重み付けサンプリングする。

        プロンプトに巨大辞書を丸ごと埋め込む代わりに、このメソッドで
        文脈に即した新鮮な候補（3〜5件）のみを動的供給する。
        """
        words = self.vocab_sets.get(genre, self.vocab_sets.get("erotic", []))
        if not words:
            return SampledVocabResult(
                category=category,
                target_intensity=intensity,
                items=[],
                count=0,
                genre=genre,
            )

        # カテゴリフィルタ
        if category and category != "all":
            pool = [w for w in words if w.category == category]
            if not pool:
                pool = words
        else:
            pool = words

        # 強度差に基づく重み付け計算（ガウス重み: 強度が近いものほど高確率）
        def _weight(w: SensoryWord) -> float:
            diff = abs(w.intensity - intensity)
            return max(0.01, 1.0 - diff)

        weights = [_weight(w) for w in pool]

        rng = random.Random(seed) if seed is not None else random.Random()

        sample_k = min(count, len(pool))
        # 重み付きサンプリング（重複なし）
        selected_indices = set()
        selected: List[SensoryWord] = []

        # 確率的選択ループ
        for _ in range(sample_k * 3):
            if len(selected) >= sample_k:
                break
            idx = rng.choices(range(len(pool)), weights=weights, k=1)[0]
            if idx not in selected_indices:
                selected_indices.add(idx)
                selected.append(pool[idx])

        # 足りない場合は単純補完
        if len(selected) < sample_k:
            for idx, w in enumerate(pool):
                if idx not in selected_indices:
                    selected.append(w)
                    if len(selected) >= sample_k:
                        break

        items = [
            {
                "word": w.word,
                "category": w.category,
                "intensity": w.intensity,
                "example_sentence": w.example_sentence,
                "nuance": w.nuance,
            }
            for w in selected
        ]

        return SampledVocabResult(
            category=category,
            target_intensity=intensity,
            items=items,
            count=len(items),
            genre=genre,
        )

    def read_resource(self, uri: str) -> str:
        """MCPリソースURIに応じた語彙辞書テキストを返す"""
        parsed = parse_vocab_uri(uri)
        if parsed.get("type") != "sensory_vocab":
            return f"Unsupported or invalid vocabulary URI: {uri}"

        genre = parsed.get("genre", "general")
        words = self.vocab_sets.get(genre, [])
        if not words:
            return f"No vocabulary found for genre: {genre}"

        lines = [f"=== Sensory & Rhetoric Vocabulary for [{genre.upper()}] ==="]
        for w in words:
            lines.append(f"- [{w.category.upper()}] {w.word} (Intensity: {w.intensity}): \"{w.example_sentence}\"")

        return "\n".join(lines)

    def suggest_metaphors(
        self,
        keyword: str,
        genre: str = "general",
        intensity: Optional[float] = None,
    ) -> List[str]:
        """キーワードに関連する感覚表現や比喩案を抽出する（強度フィルタ対応）"""
        words = self.vocab_sets.get(genre, self.vocab_sets.get("erotic", []))
        suggestions = []
        for w in words:
            if keyword in w.word or keyword in w.example_sentence or keyword in w.nuance:
                if intensity is not None and abs(w.intensity - intensity) > 0.4:
                    continue
                suggestions.append(f"{w.word} ({w.category}, 強度:{w.intensity}): {w.example_sentence}")
        return suggestions

