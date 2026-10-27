"""services/prose: FewShot選択・本文分割・段落インデックス・パッチ統合・SNS演出。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.prose.few_shot_selector import FewShotSelector
from src.services.prose.novel_output_splitter import NovelOutputSplitter
from src.services.prose.paragraph_indexer import ParagraphIndexer
from src.services.prose.patch_merger import PatchMerger
from src.services.prose.social_reaction_generator import SocialReactionGenerator

SAMPLES = {
    "fantasy_action": [
        {"before": "彼は走った", "after": "走る"},
        {"before": "彼は剣を振った", "after": "振る"},
        {"before": "彼は攻撃を避けた", "after": "避ける"},
    ],
    "villainess_court": [
        {"before": "彼女は言葉を交わした", "after": "話す"},
        {"before": "彼は考えた", "after": "思う"},
    ],
}


@pytest.fixture
def selector(tmp_path):
    p = tmp_path / "fs.json"
    p.write_text(json.dumps(SAMPLES), encoding="utf-8")
    return FewShotSelector(str(p))


def test_few_shot_missing_file(tmp_path):
    s = FewShotSelector(str(tmp_path / "nope.json"))
    assert s.get_available_genres() == []
    assert s.select_few_shots("g", "action") == []


def test_few_shot_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        FewShotSelector(str(p))


def test_few_shot_default_path_exists():
    s = FewShotSelector()
    assert s.few_shots_path.endswith("genre_few_shots.json")
    assert isinstance(s.get_available_genres(), list)


def test_few_shot_selection(selector):
    assert set(selector.get_available_genres()) == {"fantasy_action", "villainess_court"}
    out = selector.select_few_shots("fantasy_action", "action", max_examples=2)
    assert len(out) == 2
    assert out[0]["before"] == "彼は走った"


def test_few_shot_fallback_genre_and_scene(selector):
    out = selector.select_few_shots("unknown", "unknown_scene", max_examples=1)
    assert len(out) == 1
    out2 = selector.select_few_shots("villainess_court", "internal_monologue", max_examples=2)
    assert len(out2) == 2
    assert len(selector.select_few_shots("fantasy_action", "action", max_examples=5)) == 3


def test_few_shot_reload(tmp_path):
    p = tmp_path / "fs.json"
    p.write_text(json.dumps(SAMPLES), encoding="utf-8")
    s = FewShotSelector(str(p))
    p.write_text(json.dumps({"other": [{"before": "x", "after": "y"}]}), encoding="utf-8")
    s.reload()
    assert s.get_available_genres() == ["other"]


# --------------------------------------------------------------------------
def test_splitter_plain_text():
    prose, meta = NovelOutputSplitter.split_novel_output("本文だけ")
    assert prose == "本文だけ"
    assert meta is None
    assert NovelOutputSplitter.split_novel_output("") == ("", None)


def test_splitter_tagged_metadata():
    raw = (
        "物語本文です。\n\n"
        '[METADATA_JSON]\n{"episode_number": 1, "summary": "s"}\n[/METADATA_JSON]\n\n---\n'
    )
    prose, meta = NovelOutputSplitter.split_novel_output(raw)
    assert prose == "物語本文です。"
    assert meta is not None
    assert meta.episode_number == 1


def test_splitter_tagged_with_codefence():
    raw = 'T\n[METADATA_JSON]\n```json\n{"episode_number": 2}\n```\n[/METADATA_JSON]'
    prose, meta = NovelOutputSplitter.split_novel_output(raw)
    assert prose == "T"
    assert meta.episode_number == 2


def test_splitter_trailing_json_block():
    raw = 'T\n```json\n{"episode_number": 3, "extra": 1}\n```'
    prose, meta = NovelOutputSplitter.split_novel_output(raw)
    assert prose == "T"
    assert meta.episode_number == 3


def test_splitter_invalid_json_metadata():
    raw = 'T\n[METADATA_JSON]\nnot json\n[/METADATA_JSON]'
    prose, meta = NovelOutputSplitter.split_novel_output(raw)
    assert prose == "T"
    assert meta is None


def test_splitter_schema_violation_metadata():
    raw = 'T\n[METADATA_JSON]\n{"unknown_field": 1}\n[/METADATA_JSON]'
    _, meta = NovelOutputSplitter.split_novel_output(raw)
    assert meta is None


# --------------------------------------------------------------------------
def test_paragraph_indexer():
    idx = ParagraphIndexer()
    out = idx.index_paragraphs("  a  \n\n b \n\n\n\n\n c ")
    assert [o["index"] for o in out] == [0, 1, 2]
    assert out[1]["text"] == "b"
    assert idx.index_paragraphs("") == []


def test_patch_merger_noop():
    m = PatchMerger()
    assert m.merge_patches("", []) == ""
    assert m.merge_patches("a", []) == "a"
    assert m.merge_patches("a\n\n\n\n", []) == "a\n\n\n\n"
    assert m.merge_patches("   \n\n  ", [MagicMock(index=0, patched_text="x")]) == "   \n\n  "


def test_patch_merger_applies():
    from src.models.patch_pdca import PatchRewriteResult

    m = PatchMerger()
    original = "p0\n\np1\n\np2"
    patches = [
        PatchRewriteResult(index=1, patched_text="NEW1", confidence_score=0.9),
        PatchRewriteResult(index=1, patched_text="NEW1b", confidence_score=0.9),
        PatchRewriteResult(index=9, patched_text="ignored", confidence_score=0.5),
        MagicMock(index=0, patched_text=None),
    ]
    out = m.merge_patches(original, patches)
    assert out == "p0\n\nNEW1b\n\np2"


# --------------------------------------------------------------------------
async def test_social_stream_comments_success():
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=json.dumps(
        {"comments": [{"user": "a", "text": "t", "timestamp": "2024"}, {"text": "t2", "timestamp": "2024-01-01"}]}
    ))
    g = SocialReactionGenerator(llm)
    out = await g.generate_stream_comments("highlight", count=5)
    assert len(out) == 2
    assert out[1].user == "匿名"
    assert "5件" in llm.generate_text.await_args.kwargs["prompt"]


async def test_social_stream_comments_fallback():
    llm = MagicMock()
    llm.generate_text = AsyncMock(side_effect=RuntimeError("x"))
    g = SocialReactionGenerator(llm)
    out = await g.generate_stream_comments("h", count=3)
    assert len(out) == 3
    assert out[0].user == "視聴者1"


async def test_social_forum_posts_success():
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value=json.dumps({"posts": [{"name": "n", "body": "b"}, {}]}))
    g = SocialReactionGenerator(llm)
    out = await g.generate_forum_thread("h", post_count=2)
    assert [p.res_num for p in out] == [1, 2]
    assert out[1].name == "名無し"


async def test_social_forum_posts_fallback():
    llm = MagicMock()
    llm.generate_text = AsyncMock(return_value="not json")
    g = SocialReactionGenerator(llm)
    out = await g.generate_forum_thread("h", post_count=4)
    assert len(out) == 4
    assert out[0].name == "名無しさん   1"
