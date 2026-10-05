"""services/compression: Layer1/2/3/4 と日本語トークナイザのカバレッジ。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.compression import layer1_keywords as l1
from src.services.compression.japanese_tokenizer import (
    SUDACHI_AVAILABLE,
    HybridJapaneseTokenizer,
    RegexJapaneseTokenizer,
    SudachiConfig,
    SudachiTokenizer,
    TokenInfo,
    create_japanese_tokenizer,
)
from src.services.compression.layer1_keywords import (
    BM25Extractor,
    KeyBERTExtractor,
    KeyphraseExtractor,
    Layer1KeywordExtractor,
    TFIDFExtractor,
    count_tokens,
    create_extractor,
    extract_keyphrases,
    tokenize_japanese_words,
)
from src.services.compression.layer2_subgraph import (
    RELATION_WEIGHTS,
    Layer2SubgraphExtractor,
)
from src.services.compression.layer3_abstraction import (
    CONCEPT_TAXONOMY,
    DEFAULT_CATEGORIES,
    Layer3ConceptAbstractor,
)
from src.services.compression.layer4_trimming import (
    SCENE_CATEGORY_WEIGHTS,
    SCENE_KEYWORDS_WEIGHTED,
    SCENE_TRANSITION_MATRIX,
    Layer4DynamicTrimmer,
    Layer4SceneTrimmer,
    _blend_category_weights,
    _softmax,
)
from src.services.compression.models import (
    AbstractionLayerOutput,
    ProtectedContext,
    SceneFlowHistory,
    SubgraphLayerOutput,
    SudachiConfig as PydanticSudachiConfig,
)

TEXT = (
    "アルトは魔導剣を抜刀し、魔王と決闘した。"
    "ルナは火球の魔術で敵を撃破した。"
    "聖剣arteが彼の手の中にある。"
)


# --------------------------------------------------------------------------
# japanese_tokenizer.py
# --------------------------------------------------------------------------
def test_regex_tokenizer():
    t = RegexJapaneseTokenizer()
    assert t.extract_nouns("") == []
    out = t.extract_nouns("魔導剣とルナがXYZ平原に到達した。")
    assert "魔導剣" in out
    assert "XYZ" in out
    assert "の" not in out
    short = t.extract_nouns("あいうえおかきくけこさしすせそ", min_length=20)
    assert short == []
    assert t.extract_nouns("1234 5678", min_length=2) is not None


def test_sudachi_tokenizer():
    if not SUDACHI_AVAILABLE:
        pytest.skip("sudachipy not installed")
    t = SudachiTokenizer(SudachiConfig(split_mode="C"))
    assert t.tokenize("") == []
    tokens = t.tokenize("魔導剣を抜刀した")
    assert tokens
    assert isinstance(tokens[0], TokenInfo)
    nouns = t.extract_nouns("魔導剣と聖剣arteを抜刀した")
    assert nouns
    assert t.extract_nouns("") == []
    filtered = t.extract_nouns("アルトとXYZ", include_proper=False)
    assert isinstance(filtered, list)


def test_hybrid_tokenizer():
    t = HybridJapaneseTokenizer()
    assert t.extract_nouns("") == []
    out = t.extract_nouns("魔導剣aldousと聖剣arteを抜刀した")
    assert out
    assert t._regex is not None
    if SUDACHI_AVAILABLE:
        assert t._sudachi is not None
    else:
        assert t._sudachi is None


def test_create_japanese_tokenizer(monkeypatch):
    t = create_japanese_tokenizer()
    assert isinstance(t, (RegexJapaneseTokenizer, HybridJapaneseTokenizer))

    import src.services.compression.japanese_tokenizer as mod

    monkeypatch.setattr(mod, "SUDACHI_AVAILABLE", False)
    assert isinstance(create_japanese_tokenizer(), RegexJapaneseTokenizer)

    monkeypatch.setattr(mod, "SUDACHI_AVAILABLE", True)
    monkeypatch.setattr(
        mod, "HybridJapaneseTokenizer", MagicMock(side_effect=RuntimeError("boom"))
    )
    assert isinstance(create_japanese_tokenizer(), RegexJapaneseTokenizer)


def test_sudachi_tokenizer_init_failure(monkeypatch):
    if not SUDACHI_AVAILABLE:
        pytest.skip("sudachipy not installed")
    import src.services.compression.japanese_tokenizer as mod

    monkeypatch.setattr(mod.dictionary, "Dictionary", MagicMock(side_effect=RuntimeError("x")))
    with pytest.raises(RuntimeError):
        SudachiTokenizer()


# --------------------------------------------------------------------------
# layer1_keywords.py
# --------------------------------------------------------------------------
def test_count_tokens():
    assert count_tokens("") == 0
    assert count_tokens("魔導剣") > 0


def test_count_tokens_fallback(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "tiktoken", None)
    monkeypatch.setattr(l1, "_tiktoken_encoder", None)
    assert count_tokens("abcd") >= 1


def test_layer1_extract_empty_and_default_tokenizer():
    e = Layer1KeywordExtractor()
    assert e.extract("").extracted_keywords == []
    assert e.extract("   ").original_char_count == 0
    assert isinstance(tokenize_japanese_words("魔導剣"), list)


def test_layer1_extract_real_text():
    e = Layer1KeywordExtractor(top_n=5)
    out = e.extract(TEXT)
    assert out.original_char_count == len(TEXT)
    assert out.original_token_count > 0
    assert len(out.extracted_keywords) <= 5
    assert set(out.extracted_keywords) == set(out.keyword_scores)


def test_layer1_with_custom_config_and_top_n():
    e = Layer1KeywordExtractor(tokenizer_config=PydanticSudachiConfig(min_length=3))
    out = e.extract(TEXT, top_n=3)
    assert len(out.extracted_keywords) <= 3
    out2 = e.extract(TEXT, top_n=1)
    assert len(out2.extracted_keywords) <= 1


def test_layer1_no_tokens_branch(monkeypatch):
    e = Layer1KeywordExtractor()
    monkeypatch.setattr(e, "_get_tokenizer", lambda: MagicMock(extract_nouns=lambda *a, **k: []))
    out = e.extract("abc")
    assert out.extracted_keywords == []
    assert out.original_char_count == 3


def test_layer1_frequency_branch(monkeypatch):
    monkeypatch.setattr(l1, "BM25Okapi", None)
    out = Layer1KeywordExtractor().extract(TEXT)
    assert out.extracted_keywords


def test_layer1_bm25_branch(monkeypatch):
    class FakeBM25:
        def __init__(self, corpus):
            self.idf = {t: 0.01 for t in {x for c in corpus for x in c}}

    monkeypatch.setattr(l1, "BM25Okapi", FakeBM25)
    out = Layer1KeywordExtractor().extract(TEXT)
    assert out.extracted_keywords


def test_extract_keyphrases_function():
    assert extract_keyphrases(TEXT, top_n=3).extracted_keywords


def test_keyphrase_abstract_not_implemented():
    with pytest.raises(NotImplementedError):
        KeyphraseExtractor().extract("x")


def test_tfidf_extractor_legacy_helpers():
    ex = TFIDFExtractor()
    res = ex.extract(TEXT, top_k=3)
    assert len(res) <= 3
    nouns = ex._extract_japanese_nouns("アルトは魔導剣を持ち」。")
    assert isinstance(nouns, list)
    assert ex._is_function_word("は") is True
    assert ex._is_function_word("魔導剣") is False
    assert ex._is_function_word("12") is True
    scores = ex._compute_tfidf_scores(nouns, ["文1", "文2"], 3, 0.0)
    assert isinstance(scores, list)
    assert ex._compute_frequency_scores([], TEXT, 3, 0.0) == []
    # 実装は count/total を min_score でフィルタする仕様。min_score=0.0 なら
    # テキストに存在するトークンは必ず残る（空にはならない）。
    assert ex._compute_frequency_scores(["存在"], "存在", 3, 0.0) == [("存在", 1.0)]
    # min_score を相対スコアより大きな値にすれば空になる。
    assert ex._compute_frequency_scores(["存在"], "存在", 3, 1.1) == []
    # テキストに存在しないトークンはカウントされない。
    assert ex._compute_frequency_scores(["存在しない"], "存在", 3, 0.0) == []
    freq = ex._compute_frequency_scores(["魔導剣", "魔王"], TEXT, 3, 0.0)
    assert freq


def test_bm25_extractor_legacy_helpers():
    ex = BM25Extractor()
    assert len(ex.extract(TEXT, top_k=2)) <= 2
    toks = ex._tokenize("アルトA1は魔導剣-を!")
    assert toks
    assert ex._tokenize("") == [""]


def test_keybert_extractor_without_dependency():
    assert isinstance(KeyBERTExtractor().extract(TEXT), list)


def test_create_extractor():
    assert isinstance(create_extractor("tfidf"), TFIDFExtractor)
    assert isinstance(create_extractor("bm25"), BM25Extractor)
    assert isinstance(create_extractor("keybert"), KeyBERTExtractor)
    with pytest.raises(ValueError, match="Unknown extractor method"):
        create_extractor("nope")


# --------------------------------------------------------------------------
# layer2_subgraph.py
# --------------------------------------------------------------------------
ENTITIES = [
    {"name": "アルト", "id": "n1", "labels": ["Character"], "aliases": ["アル"]},
    {"name": "魔導剣", "id": "n2", "labels": ["Item"]},
    {"name": "魔王", "id": "n3", "labels": ["Character"]},
    {"name": "聖剣", "id": "n4", "labels": ["Item"]},
]
RELATIONS = [
    {"source": "n1", "target": "n2", "type": "所持"},
    {"source": "n1", "target": "n3", "type": "敵対"},
    {"source": "n2", "target": "n4", "type": "関連"},
    {"source": "n3", "target": "n4", "type": "目撃"},
]


def test_layer2_empty_inputs():
    ex = Layer2SubgraphExtractor()
    out = ex.extract_from_memory([], [], [])
    assert out.stats["source"] == "memory_empty"
    out2 = ex.extract_from_memory(ENTITIES, RELATIONS, ["存在しない名前"])
    assert out2.stats["source"] == "no_seeds_found"


def test_layer2_memory_bfs_and_prune():
    ex = Layer2SubgraphExtractor(relevance_threshold=0.4)
    out = ex.extract_from_memory(ENTITIES, RELATIONS, ["アルト"])
    assert out.seed_entity_names == ["アルト"]
    assert {n["name"] for n in out.nodes} >= {"アルト"}
    assert out.stats["initial_edges"] == 4
    assert all("relevance_score" in e for e in out.edges)


def test_layer2_alias_seed_matching():
    ex = Layer2SubgraphExtractor()
    out = ex.extract_from_memory(ENTITIES, RELATIONS, ["アル"])
    assert out.nodes


def test_layer2_max_nodes_and_edges_caps():
    ex = Layer2SubgraphExtractor(max_nodes=1, max_edges=1, relevance_threshold=0.0)
    out = ex.extract_from_memory(ENTITIES, RELATIONS, ["アルト"])
    assert len(out.edges) <= 1
    assert len(out.nodes) <= 1
    assert out.pruned_edge_count >= 0


def test_layer2_relation_weights_used():
    ex = Layer2SubgraphExtractor(relevance_threshold=0.0)
    out = ex.prune_subgraph(
        nodes=[{"id": "n1", "name": "アルト"}],
        edges=[{"source": "n1", "target": "n2", "type": "敵対", "hop": 2}],
        seed_names=["アルト"],
        keyword_scores={},
    )
    # score = hop_decay * relation_weight * seed_boost。
    # seed_boost はエッジの source/target 名にシード名が出現したときだけ 1.3 になるが、
    # このエッジの端点は "n1"/"n2" でシード名 "アルト" を含まないため seed_boost=1.0。
    assert out.edges[0]["relevance_score"] == round(0.5 * RELATION_WEIGHTS["敵対"], 3)

    # 端点名がシード名と一致する場合は seed_boost=1.3 が掛かる。
    boosted = ex.prune_subgraph(
        nodes=[{"id": "n1", "name": "アルト"}],
        edges=[{"source": "n1", "target": "n2", "type": "敵対", "hop": 2}],
        seed_names=["n1"],
        keyword_scores={},
    )
    assert boosted.edges[0]["relevance_score"] == round(0.5 * RELATION_WEIGHTS["敵対"] * 1.3, 3)


def test_layer2_age_early_returns():
    ex = Layer2SubgraphExtractor()
    assert ex.extract_from_age(MagicMock(), "g", []).stats["source"] == "age_empty"
    assert ex.extract_from_age(MagicMock(), "", ["a"]).stats["source"] == "age_empty"
    # v5.3 以降 age_client はメソッド引数ではなくコンストラクタ注入（DI）。
    # 未注入なら keyword_scores を渡しても age_empty で早期リターンする。
    without_client = Layer2SubgraphExtractor(age_client=None)
    assert without_client.extract_from_age(
        MagicMock(), "g", ["a"], keyword_scores={"a": 1.0}
    ).stats["source"] == "age_empty"
    with_client = Layer2SubgraphExtractor(age_client=MagicMock())
    assert with_client.extract_from_age(MagicMock(), "g", [""]).seed_entity_names == [""]


def test_layer2_age_query_and_parse():
    ex = Layer2SubgraphExtractor(age_client=MagicMock())
    session = MagicMock()
    session.execute.return_value = [
        ('"アルト"', '["Character"]', '{"role": "主人公"}', '"魔導剣"', '["Item"]', '{}', '["所持"]'),
        ('"アルト"', '["Character"]', '{"role": "主人公"}', None, None, None, None),
    ]
    out = ex.extract_from_age(session, "g", ["アルト'quote"], keyword_scores={"アルト": 1.0})
    assert {n["name"] for n in out.nodes} == {"アルト", "魔導剣"}
    assert out.stats["initial_edges"] >= 1
    sql = session.execute.call_args[0][0].text
    assert "cypher(" in sql


def test_layer2_age_exception_falls_back():
    ex = Layer2SubgraphExtractor(age_client=MagicMock())
    session = MagicMock()
    session.execute.side_effect = RuntimeError("db down")
    out = ex.extract_from_age(session, "g", ["アルト"])
    assert out.nodes == []


# --------------------------------------------------------------------------
# layer3_abstraction.py
# --------------------------------------------------------------------------
def _subgraph():
    return SubgraphLayerOutput(
        nodes=[
            {"id": "n1", "name": "抜刀", "labels": ["Skill"], "properties": {}},
            {"id": "n2", "name": "王都", "labels": ["Location"], "properties": {"role": "首都"}},
            {"id": "n3", "name": "聖剣", "labels": ["Item"], "properties": {}},
            {"id": "n4", "name": "関税法", "labels": ["Rule"], "properties": {}},
            {"id": "n5", "name": "謎の人物X", "labels": [], "properties": {}},
        ],
        edges=[
            {"source": "n1", "target": "n2", "type": "敵対"},
            {"source": "n1", "target": "n3", "type": "所持"},
            {"source": "n1", "target": "n4", "type": "統治"},
            {"source": "n2", "target": "n3", "type": "同盟"},
            {"source": "n3", "target": "n4", "type": "血縁"},
            {"source": "n4", "target": "n5", "type": "謎"},
        ],
    )


def test_layer3_abstract_full():
    a = Layer3ConceptAbstractor()
    out = a.abstract(_subgraph(), raw_text="聖剣arteは伝承の遺物である")
    assert set(out.categorized_facts) <= set(DEFAULT_CATEGORIES)
    assert out.abstract_concepts
    assert out.metadata["engine"] == "DynamicTaxonomyEngine"
    assert out.metadata["total_concepts"] == len(out.abstract_concepts)
    assert "cache_size" in out.metadata
    total = sum(len(f) for f in out.categorized_facts.values())
    assert total == 11


def test_layer3_empty_subgraph():
    out = Layer3ConceptAbstractor().abstract(SubgraphLayerOutput())
    assert out.categorized_facts == {}
    assert out.abstract_concepts == []


def test_layer3_custom_categories():
    a = Layer3ConceptAbstractor(categories=["主要キャラ"])
    out = a.abstract(_subgraph())
    assert set(out.categorized_facts) <= {"主要キャラ"}


def test_layer3_detect_category_heuristics():
    a = Layer3ConceptAbstractor()
    assert a._detect_category_for_node(["Place"], None, "x") == "地理・勢力"
    assert a._detect_category_for_node(["Weapon"], None, "x") == "アイテム・装備"
    assert a._detect_category_for_node(["Magic"], None, "x") == "武術・スキル"
    assert a._detect_category_for_node(["Lore"], None, "x") == "核心設定"
    assert a._detect_category_for_node([], "近接剣術スキル", "x") == "武術・スキル"
    assert a._detect_category_for_node([], "国家間外交協定", "x") == "地理・勢力"
    assert a._detect_category_for_node([], "伝説級武装", "x") == "アイテム・装備"
    assert a._detect_category_for_node([], "経済統制政策", "x") == "核心設定"
    assert a._detect_category_for_node([], None, "x") == "主要キャラ"


def test_layer3_generalize_relation():
    a = Layer3ConceptAbstractor()
    assert a._generalize_relation("") == "一般関係"
    assert a._generalize_relation(None) == "一般関係"
    assert a._generalize_relation("敵対") == "対立・因縁関係"
    assert a._generalize_relation("所属") == "統治・主従関係"
    assert a._generalize_relation("所持") == "装備・使役関係"
    assert a._generalize_relation("同盟") == "協力・盟約関係"
    assert a._generalize_relation("親子") == "血縁・家系関係"
    assert a._generalize_relation("謎") == "謎"


def test_layer3_generalize_concept():
    a = Layer3ConceptAbstractor()
    assert a._generalize_concept("抜刀") == CONCEPT_TAXONOMY["抜刀"]
    assert a._generalize_concept("未知の文字列") is None


# --------------------------------------------------------------------------
# layer4_trimming.py
# --------------------------------------------------------------------------
def test_softmax_and_blend():
    assert _softmax({}) == {}
    probs = _softmax({"a": 1.0, "b": 2.0})
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs["b"] > probs["a"]
    assert _blend_category_weights({}) == {}
    assert _blend_category_weights({"combat": 0.0}) == {}
    blended = _blend_category_weights({"combat": 1.0, "romance": 1.0})
    assert set(blended) == set(SCENE_CATEGORY_WEIGHTS["combat"])
    assert _blend_category_weights({"unknown_scene": 1.0})["主要キャラ"] == pytest.approx(1.8)


def test_detect_scene_type():
    t = Layer4SceneTrimmer()
    assert t.detect_scene_type("何もない文章") == "general"
    assert t.detect_scene_type("魔王と決闘し斬り合った") == "combat"
    assert t.detect_scene_type("酒場で雑談", scenes=["食事"]) == "daily"
    multi = t.detect_scene_type_multi("決闘と密室推理")
    assert multi[0][0] in ("combat", "mystery")
    assert sum(p for _, p in multi) == pytest.approx(1.0)


def test_detect_scene_context_aware():
    t = Layer4SceneTrimmer()
    flow = SceneFlowHistory(recent_scene_types=["flashback"], episode_goal="心理の葛藤")
    out = t.detect_scene_context_aware("回忆の記憶", scene_flow=flow)
    assert out
    assert out == sorted(out, key=lambda x: x[1], reverse=True)
    no_flow = t.detect_scene_context_aware("何もない")
    assert no_flow[0][0] == "general"


def test_trim_basic():
    t = Layer4SceneTrimmer(max_tokens=200)
    abstraction = AbstractionLayerOutput(
        abstract_concepts=["近接剣術スキル"],
        categorized_facts={
            "武術・スキル": [{"entity": "抜刀", "fact": "抜刀 [近接剣術スキル]", "dual_name": "抜刀 [近接剣術スキル]"}],
            "主要キャラ": [{"entity": "アルト", "fact": "アルト（主人公）", "dual_name": "アルト（主人公）"}],
        },
    )
    out = t.trim(abstraction, scene_type="combat", original_token_count=100)
    assert "【武術・スキル】" in out.compressed_text
    assert "【シーン主要概念】" in out.compressed_text
    assert out.reduction_ratio > 0
    assert 0.0 < out.retention_rate <= 1.0
    assert out.scene_type == "combat"


def test_trim_with_keywords_and_scene_weights():
    t = Layer4SceneTrimmer()
    abstraction = AbstractionLayerOutput(
        abstract_concepts=[],
        categorized_facts={
            "地理・勢力": [{"entity": "王都", "fact": "王都は首都", "dual_name": "王都は首都"}],
            "主要キャラ": [{"entity": "アルト", "fact": "アルト", "dual_name": "アルト"}],
        },
    )
    out = t.trim(
        abstraction,
        scene_weights={"political": 2.0, "combat": 0.5},
        keywords=["王都"],
        original_token_count=50,
    )
    assert out.scene_type == "political"
    assert out.token_count > 0


def test_trim_pinned_context_variants():
    t = Layer4SceneTrimmer(max_tokens=500)
    facts = {
        "主要キャラ": [{"entity": "アルト", "fact": "アルトは主人公", "dual_name": "アルトは主人公"}],
        "伏線": [{"entity": "FS1", "fact": "伏線FS1が張られた", "dual_name": "伏線FS1が張られた"}],
        "アイテム・装備": [{"entity": "聖剣", "fact": "聖剣を所持", "dual_name": "聖剣を所持"}],
        "地理・勢力": [{"entity": "王都", "fact": "王都は首都", "dual_name": "王都は首都"}],
    }
    abstraction = AbstractionLayerOutput(abstract_concepts=["c"], categorized_facts=facts)

    out = t.trim(
        abstraction,
        protected_context=ProtectedContext(
            active_characters=["アルト"],
            pending_foreshadowing_ids=["FS1"],
            pinned_entities={"聖剣"},
            critical_keywords=["王都"],
        ),
    )
    assert out.pinned_count == 4
    assert "【現在同席】" in out.compressed_text
    assert "【最重要伏線】" in out.compressed_text
    assert "【必須注視】" in out.compressed_text


def test_trim_tight_budget_trims_concepts():
    t = Layer4SceneTrimmer()
    abstraction = AbstractionLayerOutput(
        abstract_concepts=[f"概念{i}" for i in range(10)],
        categorized_facts={
            "主要キャラ": [
                {"entity": f"E{i}", "fact": f"事実{i} " * 5, "dual_name": f"E{i}"}
                for i in range(5)
            ]
        },
    )
    out = t.trim(abstraction, max_tokens=20)
    assert out.token_count <= 40


def test_trim_all_pinned_cannot_reduce():
    """Step 56: 残りが全てピン留めなら予算超過分を削れず、そのまま保持する。

    2026-10-05: 旧テストは `assert out.token_count > 300` と絶対値を
    ハードコードしていたが、`count_tokens()` は tiktoken があれば BPE
    （`"F"*200` → 25 トークン）、無ければ `len(text) * 1.5`（→ 300）に
    フォールバックする。tiktoken は必須依存なので CI では常に BPE 経路となり、
    旧アサーションは構造的に成立しModeling 있었다。

    そこで期待値を**実装の権威ある源**（`count_tokens()`）から導出し、
    さらにトークン計算に一切依存しない不変条件
    （"ピン留めされた事実は1バイトも削られていない"）を併せて固定する。
    """
    t = Layer4SceneTrimmer()
    fact = "F" * 200
    abstraction = AbstractionLayerOutput(
        abstract_concepts=[],
        categorized_facts={
            "主要キャラ": [{"entity": "E", "fact": fact, "dual_name": "E"}],
        },
    )
    protected = ProtectedContext(active_characters=["E"])

    # 事実自体のトークン数を予算にして採用され、整形結果だけが予算を超える
    budget = count_tokens(fact)
    out = t.trim(abstraction, max_tokens=budget, protected_context=protected)

    assert out.pinned_count == 1
    # 予算tokens には、「予算を超えた」ことが要以「的事实の完全保持」で担保する
    # （絶対 token 数は tiktoken 依存のため比較しない）
    assert fact in out.compressed_text, "ピン留めされた事実が削られている"
    assert out.token_count >= budget

    # なお初期採用の予算ゲートはピン留めでも効く（予算が事実1件にも満たない場合は採用されない）。
    tiny = t.trim(abstraction, max_tokens=1, protected_context=protected)
    assert tiny.pinned_count == 0


def test_trim_all_pinned_keeps_fact_byte_identical():
    """トークナイザに一切依存しない不変条件：ピン留め事実は byte 単位で保持される。

    `test_trim_all_pinned_cannot_reduce` の tiktoken 依存部分
    （max_tokens の与え方）を除いた「本质的な契約」だけを単独で固定する。
    tiktoken 有無の両方で成立するため、
    BPE とフォールバックのどちらが混ざっても緑になる。
    """
    t = Layer4SceneTrimmer()
    fact = "F" * 200
    abstraction = AbstractionLayerOutput(
        abstract_concepts=[],
        categorized_facts={
            "主要キャラ": [{"entity": "E", "fact": fact, "dual_name": "E"}],
        },
    )
    protected = ProtectedContext(active_characters=["E"])

    for budget in (1, 10, count_tokens(fact), 10_000):
        out = t.trim(abstraction, max_tokens=budget, protected_context=protected)
        if out.pinned_count:
            assert fact in out.compressed_text, (
                f"予算={budget} でピン留め事実が削られた: "
                f"{len(out.compressed_text)} 文字"
            )


class TestCountTokensBackends:
    """`count_tokens()` の両バックエンドの契約を固定する。

    現状 tiktoken なし（フォールバック）経路のテストが 1 件も無く、
    「どちらの経路で動いても正しい」ことが検証されていない。
    """

    def test_fallback_is_length_times_one_point_five(self, monkeypatch):
        """tiktoken が import できない場合、`len(text) * 1.5` にフォールバックすること。"""
        import builtins

        real_import = builtins.__import__

        def _fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken" or name.startswith("tiktoken."):
                raise ImportError("tiktoken unavailable (test)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_tiktoken)

        text = "a" * 100
        assert count_tokens(text) == int(len(text) * 1.5)

    def test_empty_string_returns_zero(self, monkeypatch):
        """空文字列は 0 を返す（両バックエンドに依らず）。

        `count_tokens` は先頭で `if not text: return 0` するため、
        tiktoken があってもなくても 0。フォールバックの
        `max(1, ...)` より**前**に短絡される点に注意。
        """
        import builtins

        real_import = builtins.__import__

        def _fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken" or name.startswith("tiktoken."):
                raise ImportError("tiktoken unavailable (test)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_tiktoken)
        assert count_tokens("") == 0

    def test_fallback_never_returns_zero_for_non_empty(self, monkeypatch):
        """非空文字列ではフォールバックが 0 を返さないこと。

        `max(1, int(len(text) * 1.5))` により、少なくとも 1 は返る。
        0 が返ると「予算判定で常に圧縮缓解」になる。
        """
        import builtins

        real_import = builtins.__import__

        def _fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken" or name.startswith("tiktoken."):
                raise ImportError("tiktoken unavailable (test)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_tiktoken)
        for text in ("a", "短", "x" * 3):
            assert count_tokens(text) >= 1, f"非空文字列で 0 が返った: {text!r}"

    def test_monotonic_in_both_backends(self, monkeypatch):
        """どちらのバックエンドでも「長いほどトークン数が増える」こと。"""
        short, long = "a" * 50, "a" * 500

        # 通常のバックエンド（tiktoken が使えるなら BPE）
        assert count_tokens(long) >= count_tokens(short)

        # フォールバックバックエンド
        import builtins

        real_import = builtins.__import__

        def _fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken" or name.startswith("tiktoken."):
                raise ImportError("tiktoken unavailable (test)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_tiktoken)
        assert count_tokens(long) >= count_tokens(short)


def test_trim_empty_facts():
    t = Layer4SceneTrimmer()
    out = t.trim(AbstractionLayerOutput())
    assert out.compressed_text == ""
    assert out.retention_rate == 1.0
    assert out.dropped_categories == []


def test_trim_dropped_categories_reported():
    t = Layer4SceneTrimmer(max_tokens=5)
    abstraction = AbstractionLayerOutput(
        abstract_concepts=[],
        categorized_facts={
            "主要キャラ": [{"entity": "A", "fact": "A" * 100, "dual_name": "A"}],
            "地理・勢力": [{"entity": "B", "fact": "B" * 100, "dual_name": "B"}],
        },
    )
    out = t.trim(abstraction, scene_type="combat")
    assert out.dropped_categories


def test_layer4_alias_export():
    assert Layer4DynamicTrimmer is Layer4SceneTrimmer
    assert set(SCENE_TRANSITION_MATRIX) >= {"combat", "general"}
    assert "決闘" in SCENE_KEYWORDS_WEIGHTED["combat"]
