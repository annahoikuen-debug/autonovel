"""src/agents/enrichment/sensory.py の単体テスト."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.agents.enrichment.sensory import (
    EmotionSpan,
    _call_llm_async,
    _fallback_sensory_details,
    detect_abstract_emotions,
    detect_trailing_conjunction,
    expand_sensory_details_pipeline,
    extract_sentence_span,
    generate_sensory_details,
    is_inside_dialogue,
    replace_with_sensory_expansion,
    sanitize_punctuation,
    validate_rewritten_sentence,
)


def _span(emotion="sadness", start=0, end=0, sentence_text="", conj="", phrase="x"):
    return EmotionSpan(
        start=start,
        end=end,
        emotion=emotion,
        intensity=0.7,
        abstract_phrase=phrase,
        sentence_start=start,
        sentence_end=end + 1,
        sentence_text=sentence_text,
        trailing_conjunction=conj,
    )


# --------------------------------------------------------------- helpers


def test_extract_sentence_span():
    text = "前の文。感情の文！次？\n末"
    start, end, sentence = extract_sentence_span(text, 5, 7)
    assert text[start:end] == "感情の文！"
    assert sentence == "感情の文！"


def test_extract_sentence_span_no_delims():
    start, end, sentence = extract_sentence_span("感情の文", 1, 3)
    assert start == 0
    assert end == len("感情の文")
    assert sentence == "感情の文"


def test_detect_trailing_conjunction():
    assert detect_trailing_conjunction("悲しかったが、笑った", 5) == "が、"


    assert detect_trailing_conjunction("悲しかったので", 5) == "ので"
    assert detect_trailing_conjunction("そのまま進んだ", 4) == ""


def test_is_inside_dialogue():
    assert is_inside_dialogue("「、台詞」内的", 2) is True
    assert is_inside_dialogue("地の文", 2) is False
    assert is_inside_dialogue("『本』", 1) is True
    assert is_inside_dialogue("」「", 1) is False
    assert is_inside_dialogue("『本』内の台詞", 6) is False


def test_detect_abstract_emotions_drops_overlapping_matches():
    # 「悲し」 と 「悲しかった」 が重複し、後者优先されるため1件のみ残る
    spans = detect_abstract_emotions("彼は悲しかった。")
    assert len(spans) == 1


def test_detect_abstract_emotions_skips_overlapping_match():
    # 感情語が重なり、区間が重複するマッチは1件に丸められる
    text = "感激怒った。"
    spans = detect_abstract_emotions(text)
    assert len(spans) == 1
    assert (spans[0].emotion, spans[0].start, spans[0].end) == ("anger", 1, 3)


@pytest.mark.parametrize("context,first_sense", [("炎の火が燃える", "tactile"), ("闇の影", "visual"), ("森の外の風", "tactile")])
async def test_generate_sensory_details_context_priorities(context, first_sense):
    details = await generate_sensory_details(_span(), context)
    assert details[0].startswith(f"[{first_sense}]")


def test_detect_abstract_emotions_basic():
    text = "彼は悲しかった。"
    spans = detect_abstract_emotions(text)
    assert spans
    assert spans[0].emotion == "sadness"
    assert spans[0].sentence_text == text
    assert spans[0].trailing_conjunction == ""


def test_detect_abstract_emotions_skips_dialogue():
    text = "「私は悲しい」と彼は言った。"
    assert detect_abstract_emotions(text, skip_dialogue=True) == []
    assert len(detect_abstract_emotions(text, skip_dialogue=False)) >= 1


def test_detect_abstract_emotions_captures_conjunction_and_sentence():
    text = "雨のなか彼は悲しかったが、静かに歩いた。"
    spans = detect_abstract_emotions(text)
    conj = [s.trailing_conjunction for s in spans if s.trailing_conjunction]
    assert conj


def test_detect_abstract_emotions_no_match():
    assert detect_abstract_emotions("何でもない文章") == []


# ------------------------------------------------------------- LLM adapter


async def test_call_llm_generate_sync():
    assert await _call_llm_async(MagicMock(generate=MagicMock(return_value="x")), "p") == "x"


async def test_call_llm_generate_async_with_content():
    class Res:
        content = "from content"

    class LLM:
        async def generate(self, prompt):
            return Res()

    assert await _call_llm_async(LLM(), "p") == "from content"


async def test_call_llm_ainvoke():
    class LLM:
        async def ainvoke(self, prompt):
            return "ai"

    assert await _call_llm_async(LLM(), "p") == "ai"


async def test_call_llm_agenerate():
    class LLM:
        async def agenerate(self, prompt):
            return "ag"

    assert await _call_llm_async(LLM(), "p") == "ag"


async def test_call_llm_callable():
    async def fn(prompt):
        return "cb"

    assert await _call_llm_async(fn, "p") == "cb"


async def test_call_llm_unsupported():
    with pytest.raises(TypeError, match="Unsupported LLM object type"):
        await _call_llm_async(object(), "p")


# ------------------------------------------------------- generate_sensory


def test_fallback_sensory_details():
    span = _span()
    out = _fallback_sensory_details(span, ["visual", "nonexistent"], {"visual": ["赤い"]})
    assert out == ["[visual] 赤い"]


async def test_generate_sensory_details_fallback():
    span = _span()
    details = await generate_sensory_details(span, "何でもない")
    assert details
    assert all(d.startswith("[") for d in details)


async def test_generate_sensory_details_unknown_emotion_returns_empty():
    span = _span(emotion="unknown_emotion")
    assert await generate_sensory_details(span, "雨の部屋") == []


async def test_generate_sensory_details_with_llm_success(monkeypatch):
    class LLM:
        async def generate(self, prompt):
            return "[visual] 赤い世界。[auditory] 音"

    span = _span()
    details = await generate_sensory_details(span, "雨", llm=LLM())
    assert details == ["赤い世界。音"]


async def test_generate_sensory_details_llm_short_output_falls_back():
    class LLM:
        async def generate(self, prompt):
            return "ab"

    span = _span()
    details = await generate_sensory_details(span, "雨", llm=LLM())
    assert all(d.startswith("[") for d in details)


async def test_generate_sensory_details_llm_error_falls_back():
    class LLM:
        async def generate(self, prompt):
            raise RuntimeError("boom")

    span = _span()
    details = await generate_sensory_details(span, "雨", llm=LLM())
    assert details


async def test_generate_sensory_details_llm_timeout_falls_back(monkeypatch):
    class LLM:
        async def generate(self, prompt):
            await asyncio.sleep(5)

    span = _span()
    details = await generate_sensory_details(span, "雨", llm=LLM(), timeout_seconds=0.01)
    assert details


async def test_generate_sensory_details_uses_prompt_manager(monkeypatch):
    class FakeTpl:
        source = "{{emotion}}|{{scene_context}}|{{pov}}"

    pm = MagicMock()
    pm.get_template.return_value = FakeTpl()
    seen = {}

    class LLM:
        async def generate(self, prompt):
            seen["prompt"] = prompt
            return "十分に長い出力です"

    span = _span()
    out = await generate_sensory_details(span, "雨", llm=LLM(), prompt_manager=pm)
    assert out == ["十分に長い出力です"]
    assert "sadness" in seen["prompt"]


async def test_generate_sensory_details_prompt_manager_raises(monkeypatch):
    pm = MagicMock()
    pm.get_template.side_effect = RuntimeError("no template")

    class LLM:
        async def generate(self, prompt):
            return "十分に長い出力です"

    out = await generate_sensory_details(_span(), "雨", llm=LLM(), prompt_manager=pm)
    assert out == ["十分に長い出力です"]


async def test_generate_sensory_details_no_template_found(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    seen = {}

    class LLM:
        async def generate(self, prompt):
            seen["prompt"] = prompt
            return "十分に長い出力です"

    out = await generate_sensory_details(_span(), "雨", llm=LLM())
    assert out == ["十分に長い出力です"]
    # テンプレートが無い場合はインラインプロンプトになる
    assert "小説の地の文リライト" in seen["prompt"]


async def test_generate_sensory_details_loads_disk_template(monkeypatch, tmp_path):
    tpl_dir = tmp_path / "prompts" / "enrichment"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "sensory_expansion.jinja2").write_text(
        "TPL:{{emotion}}:{{scene_context}}:{{trailing_conjunction}}:{{preferred_senses}}", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    seen = {}

    class LLM:
        async def generate(self, prompt):
            seen["prompt"] = prompt
            return "十分に長い出力です"

    out = await generate_sensory_details(_span(), "雨", llm=LLM())
    assert out == ["十分に長い出力です"]
    assert seen["prompt"].startswith("TPL:sadness")


# ------------------------------------------------------------- sanitizers


def test_sanitize_punctuation():
    assert sanitize_punctuation("。。テスト、、。") == "。テスト。"
    assert sanitize_punctuation("文。が、続く") == "文が、続く"
    assert sanitize_punctuation("文、。続く") == "文。続く"
    assert sanitize_punctuation("同じ。。です") == "同じ。です"
    assert sanitize_punctuation("文。。です") == "文。です"


def test_validate_rewritten_sentence():
    assert validate_rewritten_sentence("有効な文です", "orig") is True
    assert validate_rewritten_sentence("", "orig") is False
    assert validate_rewritten_sentence("ab", "orig") is False
    assert validate_rewritten_sentence("。。。", "orig") is False
    assert validate_rewritten_sentence("[object Object]", "orig") is False
    assert validate_rewritten_sentence("Error occurred", "orig") is False


# --------------------------------------------------------- replacement


def test_replace_no_spans():
    assert replace_with_sensory_expansion("テキスト", [], []) == ("テキスト", [])


def test_replace_sentence_level_with_details():
    text = "彼は悲しかった。"
    span = EmotionSpan(
        start=2,
        end=7,
        emotion="sadness",
        intensity=0.7,
        abstract_phrase="悲しかった",
        sentence_start=0,
        sentence_end=len(text),
        sentence_text=text,
    )
    out, meta = replace_with_sensory_expansion(text, [span], [["[visual] 涙がこぼれる"]])
    assert "涙がこぼれる" in out
    assert meta[0]["emotion"] == "sadness"
    assert meta[0]["senses_covered"] == ["visual"]
    assert meta[0]["position"] == 0


def test_replace_phrase_level_falls_back_to_sense_generic():
    text = "彼は悲しかった。"
    span = EmotionSpan(
        start=2, end=7, emotion="sadness", intensity=0.7, abstract_phrase="悲しかった"
    )
    out, meta = replace_with_sensory_expansion(text, [span], [["涙がこぼれる"]])
    assert meta[0]["senses_covered"] == ["sensory"]
    assert "涙がこぼれる" in out


def test_replace_empty_details_keeps_original():
    text = "彼は悲しかった。"
    span = EmotionSpan(
        start=2,
        end=7,
        emotion="sadness",
        intensity=0.7,
        abstract_phrase="悲しかった",
        sentence_start=0,
        sentence_end=len(text),
        sentence_text=text,
    )
    out, _ = replace_with_sensory_expansion(text, [span], [[]])
    assert out == text


def test_replace_invalid_expansion_rolls_back():
    text = "彼は悲しかった。"
    span = EmotionSpan(
        start=2,
        end=7,
        emotion="sadness",
        intensity=0.7,
        abstract_phrase="悲しかった",
        sentence_start=0,
        sentence_end=len(text),
        sentence_text=text,
    )
    out, _ = replace_with_sensory_expansion(text, [span], [["[visual] Error"]])
    assert out == "彼は悲しかった。"


def test_replace_appends_punctuation_and_trailing_clause():
    text = "彼は悲しかったが、静かに歩いた。"
    span = EmotionSpan(
        start=2,
        end=7,
        emotion="sadness",
        intensity=0.7,
        abstract_phrase="悲しかった",
        sentence_start=0,
        sentence_end=len(text),
        sentence_text=text,
        trailing_conjunction="が",
    )
    out, _ = replace_with_sensory_expansion(text, [span], [["[visual] 涙がこぼれる"]])
    assert "涙がこぼれる" in out
    assert "静かに歩いた" in out


def test_replace_trailing_clause_already_present():
    text = "彼は悲しかったが、静かに歩いた。"
    span = EmotionSpan(
        start=2,
        end=7,
        emotion="sadness",
        intensity=0.7,
        abstract_phrase="悲しかった",
        sentence_start=0,
        sentence_end=len(text),
        sentence_text=text,
        trailing_conjunction="が",
    )
    out, _ = replace_with_sensory_expansion(
        text, [span], [["[visual] 涙がこぼれるが、静かに歩いた"]]
    )
    assert out.count("静かに歩いた") == 1


def test_replace_multiple_spans_metadata_order():
    text = "彼は悲しかった。彼女は嬉しかった。"
    spans = detect_abstract_emotions(text)
    details = [["[visual] a"] for _ in spans]
    out, meta = replace_with_sensory_expansion(text, spans, details)
    assert len(meta) == len(spans)
    assert [m["position"] for m in meta] == sorted(m["position"] for m in meta)


# ------------------------------------------------------------- pipeline


async def test_pipeline_no_emotion_returns_text():
    assert await expand_sensory_details_pipeline("何でもない文章") == ("何でもない文章", [])


async def test_pipeline_end_to_end_fallback():
    text = "彼は悲しかった。"
    out, meta = await expand_sensory_details_pipeline(text, scene_context="雨の部屋")
    assert meta
    assert "[visual]" not in out


async def test_pipeline_with_llm():
    class LLM:
        async def generate(self, prompt):
            return "雨音だけが響いていた"

    text = "彼は悲しかった。"
    out, meta = await expand_sensory_details_pipeline(text, scene_context="雨", llm=LLM())
    assert "雨音だけが響いていた" in out
    assert meta[0]["emotion"] == "sadness"
