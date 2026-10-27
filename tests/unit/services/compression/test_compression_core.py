"""services/compression: キャッシュ・設定モデル・品質メトリクス・4層統合。"""

from __future__ import annotations

from unittest.mock import MagicMock

import yaml

from src.services.compression.cache import CompressionCache
from src.services.compression.compressor import FourLayerCompressor
from src.services.compression.metrics import calculate_consistency_metrics
from src.services.compression.models import (
    CompressionConfig,
    CompressedContextResult,
    CompressionQualityMetrics,
    CompressionResult,
    ProtectedContext,
    ReversibleEntityFact,
    SceneFlowHistory,
    SubgraphLayerOutput,
    TrimmedContextOutput,
    get_compression_config,
    load_compression_config,
)


# --------------------------------------------------------------------------
# cache.py
# --------------------------------------------------------------------------
def test_cache_make_key_is_stable():
    c = CompressionCache()
    k1 = c.make_key(1, 2, "combat", "hash")
    k2 = c.make_key(1, 2, "combat", "hash")
    assert k1 == k2
    assert k1 != c.make_key(None, None, "general", "hash")


def test_cache_memory_roundtrip():
    c = CompressionCache()
    c.set("k", {"a": 1})
    assert c.get("k") == {"a": 1}
    assert c.get("missing") is None


def test_cache_expiry():
    c = CompressionCache()
    c.set("k", {"a": 1}, ttl=-1)
    assert c.get("k") is None


def test_cache_capacity_eviction():
    c = CompressionCache()
    for i in range(1005):
        c.set(f"k{i}", {"i": i})
    assert len(c._memory_cache) <= 1000


def test_cache_redis_path():
    redis = MagicMock()
    redis.get.return_value = b'{"x": 1}'
    redis.setex.return_value = True
    c = CompressionCache(redis_client=redis)
    c.set("k", {"a": 1})
    redis.setex.assert_called_once()
    assert c.get("k") == {"x": 1}

    redis.get.return_value = '{"y": 2}'
    assert c.get("k") == {"y": 2}
    redis.get.return_value = None
    assert c.get("k") is None


def test_cache_redis_failure_falls_back_to_memory():
    redis = MagicMock()
    redis.get.side_effect = RuntimeError("down")
    redis.setex.side_effect = RuntimeError("down")
    c = CompressionCache(redis_client=redis)
    c.set("k", {"a": 1})
    assert c.get("k") == {"a": 1}


# --------------------------------------------------------------------------
# models.py
# --------------------------------------------------------------------------
def test_compression_result_compat_properties():
    from src.services.compression.models import (
        AbstractionLayerOutput,
        RawTextLayerOutput,
    )

    empty = CompressedContextResult(layer4=TrimmedContextOutput())
    assert empty.layer1_keyphrases == []
    assert empty.layer2_subgraph == {}
    assert empty.layer3_abstracted == {}
    assert empty.layer4_trimmed == ""
    assert empty.stats["from_cache"] is False

    full = CompressedContextResult(
        layer1=RawTextLayerOutput(extracted_keywords=["a", "b"], keyword_scores={"a": 0.5}),
        layer2=SubgraphLayerOutput(nodes=[{"n": 1}], edges=[{"e": 1}], stats={"s": 1}),
        layer3=AbstractionLayerOutput(categorized_facts={"c": []}),
        layer4=TrimmedContextOutput(compressed_text="text", token_count=3),
        final_context_text="text",
    )
    assert full.layer1_keyphrases == [("a", 0.5), ("b", 1.0)]
    assert full.layer2_subgraph["nodes"] == [{"n": 1}]
    assert full.layer3_abstracted == {"c": []}
    assert full.layer4_trimmed == "text"


def test_layer3_abstracted_property():
    from src.services.compression.models import AbstractionLayerOutput

    r = CompressedContextResult(
        layer3=AbstractionLayerOutput(categorized_facts={"cat": [{"f": 1}]}),
        layer4=TrimmedContextOutput(),
    )
    assert r.layer3_abstracted == {"cat": [{"f": 1}]}


def test_compression_result_alias():
    assert CompressionResult is CompressedContextResult


def test_reversible_entity_fact_display():
    f = ReversibleEntityFact(entity="抜刀", concept="雷撃", category="武術", raw_fact="x")
    assert f.display_text == "抜刀 [雷撃]"
    same = ReversibleEntityFact(entity="抜刀", concept="抜刀", category="武術", raw_fact="x")
    assert same.display_text == "抜刀"
    empty = ReversibleEntityFact(entity="e", concept="", category="c", raw_fact="r")
    assert empty.display_text == "e"


def test_protected_context_and_flow_defaults():
    pc = ProtectedContext()
    assert pc.active_characters == []
    assert pc.pinned_entities == set()
    flow = SceneFlowHistory()
    assert flow.recent_scene_types == []
    assert flow.pacing_tag == "normal"
    assert CompressionQualityMetrics().overall_consistency_score == 1.0


def test_load_compression_config_missing_file(tmp_path):
    cfg = load_compression_config(str(tmp_path / "nope.yaml"))
    assert isinstance(cfg, CompressionConfig)
    assert cfg.max_tokens == 1500


def test_load_compression_config_from_yaml(tmp_path):
    data = {
        "compression": {
            "layer1_keyphrase": {"top_k": 5, "sudachi": {"split_mode": "A", "min_length": 3}},
            "layer2_subgraph": {"max_hops": 3, "relevance_threshold": 0.9},
            "layer4_trimming": {"max_tokens": 100, "preserve_categories": ["a"]},
        }
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_compression_config(str(p))
    assert cfg.top_keywords == 5
    assert cfg.max_hops == 3
    assert cfg.relevance_threshold == 0.9
    assert cfg.max_tokens == 100
    assert cfg.preserve_categories == ["a"]
    assert cfg.sudachi.split_mode == "A"
    assert cfg.sudachi.min_length == 3


def test_load_compression_config_invalid(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("compression: [1,2", encoding="utf-8")
    assert isinstance(load_compression_config(str(p)), CompressionConfig)


def test_get_compression_config_caches(monkeypatch):
    import src.services.compression.models as m

    monkeypatch.setattr(m, "_compression_config_instance", None)
    cfg = get_compression_config()
    assert get_compression_config() is cfg


# --------------------------------------------------------------------------
# metrics.py
# --------------------------------------------------------------------------
def test_metrics_defaults_all_perfect():
    out = TrimmedContextOutput(compressed_text="", token_count=10, retained_entities=[])
    m = calculate_consistency_metrics("", out)
    assert m.character_retention_score == 1.0
    assert m.proper_noun_retention_score == 1.0
    assert m.semantic_density_score == 0.0
    assert m.overall_consistency_score == 0.9


def test_metrics_with_protected_context():
    raw = "アルトが剣を抜いた。ルナは待った。"
    out = TrimmedContextOutput(
        compressed_text="アルトが剣を抜いた。",
        token_count=5,
        retained_entities=["剣"],
    )
    pc = ProtectedContext(
        active_characters=["アルト", "不在の者"],
        pending_foreshadowing_ids=["伏線1", "伏線2"],
    )
    m = calculate_consistency_metrics(raw, out, pc)
    assert 0.0 < m.character_retention_score <= 1.0
    assert 0.0 < m.foreshadowing_retention_score <= 1.0
    assert 0.0 <= m.proper_noun_retention_score <= 1.0
    assert m.semantic_density_score == 1.0
    assert 0.0 <= m.overall_consistency_score <= 1.0


def test_metrics_no_matching_targets():
    out = TrimmedContextOutput(compressed_text="x", token_count=1, retained_entities=[])
    pc = ProtectedContext(active_characters=["ZZZ"], pending_foreshadowing_ids=["QQQ"])
    m = calculate_consistency_metrics("abc", out, pc)
    assert m.character_retention_score == 1.0
    assert m.foreshadowing_retention_score == 1.0


def test_metrics_density_cap():
    out = TrimmedContextOutput(
        compressed_text="x", token_count=1, retained_entities=[str(i) for i in range(50)]
    )
    m = calculate_consistency_metrics("テキスト", out)
    assert m.semantic_density_score == 1.0


# --------------------------------------------------------------------------
# compressor.py
# --------------------------------------------------------------------------
RAW = (
    "アルトは剣を抜いた。斬撃が空気を裂く。"
    "ルナは呪文を唱え、氷の壁を立ち上げた。"
    "暗黒の魔王が現れた。"
)


def test_compressor_end_to_end():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    res = comp.compress(RAW)
    assert isinstance(res, CompressedContextResult)
    assert res.final_context_text
    assert res.layer1 is not None
    assert res.layer2 is not None
    assert res.layer3 is not None
    assert 0.0 <= res.overall_reduction_ratio <= 1.0
    assert res.elapsed_ms >= 0.0
    assert res.metrics is not None


def test_compressor_empty_text():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    res = comp.compress("   ")
    assert res.final_context_text == ""
    assert res.final_token_count == 0
    assert res.overall_reduction_ratio == 0.0
    assert res.metrics is not None


def test_compressor_cache_roundtrip():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=True))
    first = comp.compress(RAW, book_id=1, ep_num=1)
    second = comp.compress(RAW, book_id=1, ep_num=1)
    assert first.from_cache is False
    assert second.from_cache is True

    bypassed = comp.compress(RAW, book_id=1, ep_num=1, bypass_cache=True)
    assert bypassed.from_cache is False


def test_compressor_cache_invalid_payload():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=True))
    res = comp.compress(RAW, book_id=2, ep_num=2)
    key = next(iter(comp.cache._memory_cache))
    comp.cache.set(key, {"bogus": True}, ttl=None)
    out = comp.compress(RAW, book_id=2, ep_num=2)
    assert out.from_cache is False
    assert res.final_context_text


def test_compressor_cache_set_failure(monkeypatch):
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=True))
    monkeypatch.setattr(comp.cache, "set", MagicMock(side_effect=RuntimeError("x")))
    assert comp.compress(RAW, book_id=3, ep_num=3).final_context_text


def test_compressor_with_protected_context_and_entities():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    res = comp.compress(
        RAW,
        entities=[{"name": "アルト", "labels": ["Character"]}],
        relations=[{"source": "アルト", "target": "剣", "type": "POSSESSES"}],
        protected_context=ProtectedContext(
            active_characters=["アルト"],
            pending_foreshadowing_ids=["伏線1"],
            pinned_entities={"魔王"},
        ),
    )
    assert res.final_context_text


def test_compressor_scene_flow_override():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    flow = SceneFlowHistory(recent_scene_types=["combat"], pacing_tag="confrontation")
    res = comp.compress(RAW, scene_flow=flow, scene_type="daily")
    assert res.final_context_text
    assert res.layer4.scene_type is not None


def test_compressor_max_tokens_override():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    tiny = comp.compress(RAW, max_tokens=5)
    assert tiny.final_token_count <= 5


def test_compressor_uses_age_when_available():
    age = MagicMock()
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False), age_client=age)
    session = MagicMock()
    comp.layer2.extract_from_age = MagicMock(
        return_value=SubgraphLayerOutput(seed_entity_names=["アルト"])
    )
    res = comp.compress(RAW, session=session, graph_name="g")
    comp.layer2.extract_from_age.assert_called_once()
    assert res.layer2.seed_entity_names == ["アルト"]


def test_compressor_scene_weights():
    comp = FourLayerCompressor(CompressionConfig(cache_enabled=False))
    res = comp.compress(RAW, scene_weights={"combat": 2.0, "daily": 0.5})
    assert res.final_context_text
