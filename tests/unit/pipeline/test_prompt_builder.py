"""Tests for prompt builder."""
from __future__ import annotations

import pytest

from src.stores.vector_store import RedisVectorStore
from src.pipeline.prompt_builder import build_emotional_context_prompt, build_fused_emotional_context_prompt
from src.pipeline.emotional_residue import EmotionalVector, EmotionalSignal, EmotionType


class TestPromptBuilder:
    """プロンプトビルダーテスト"""

    @pytest.fixture
    def vector_store(self):
        import fakeredis
        redis_client = fakeredis.FakeRedis(decode_responses=True)
        store = RedisVectorStore(skip_connection_check=True)
        store.client = redis_client
        return store

    @pytest.fixture
    def sample_vector(self):
        vec = EmotionalVector(episode_id="ep14")
        vec.set_signal(EmotionalSignal("A", "B", EmotionType.AFFECTION, 0.3, 0.8, "...", "ep14"))
        vec.set_signal(EmotionalSignal("A", "B", EmotionType.FEAR, 0.8, 0.9, "...", "ep14", "ep14_betrayal"))
        return vec

    def test_build_prompt(self, vector_store, sample_vector):
        """プロンプト生成テスト"""
        # 直接ベクトルを保存
        vector_store.upsert("pipeline", "ep14", sample_vector)

        prompt = build_emotional_context_prompt(15, vector_store)  # ep15執筆時 → ep14参照

        assert "直前話からの引き継ぎ感情" in prompt
        assert "A→B" in prompt
        assert "affection" in prompt
        assert "fear" in prompt

    def test_build_prompt_no_prev_episode(self, vector_store):
        """前話がない場合（ep1）"""
        prompt = build_emotional_context_prompt(1, vector_store)
        assert prompt == ""

    def test_build_prompt_no_data(self, vector_store):
        """データなしの場合"""
        prompt = build_emotional_context_prompt(99, vector_store)
        assert prompt == ""

    def test_build_fused_prompt_priority(self, vector_store, sample_vector):
        """融合プロンプト優先順位テスト"""
        from src.fusion.engine import FusionEngine

        # annotationネームスペースにデータ
        vector_store.upsert("annotation", "ep14", sample_vector)
        # pipelineにも異なるデータ
        vec2 = EmotionalVector(episode_id="ep14")
        vec2.set_signal(EmotionalSignal("A", "B", EmotionType.AFFECTION, -0.5, 0.8, "...", "ep14"))
        vector_store.upsert("pipeline", "ep14", vec2)

        # fusion_engine に FusionEngine を渡す（内部で fuse_and_persist される前提のため
        # ここでは事前に融合キャッシュを作らない: get_fused が None の場合は
        # build_fused_emotional_context_prompt が fuse_all を実行する）
        engine = FusionEngine(vector_store)

        # annotationが優先される
        prompt = build_fused_emotional_context_prompt(15, engine)

        # annotationの値（0.3）が採用される
        assert "0.3" in prompt
        # 矛盾検出セクションに pipeline 側の値が表示されることがあるため、
        # 高信頼度セクションの採用値が annotation 由来であることのみ検証
        assert "[annotation]" in prompt
