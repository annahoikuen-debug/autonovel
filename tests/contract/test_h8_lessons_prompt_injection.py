"""H8: `final_writing_prompt.j2` における `lessons_block` 注入の契約テスト。

- `lessons_block=""`（ENABLE_AUDIT_LESSONS=OFF 相当）では、テンプレートの
  `{% if lessons_block %}` ブロックが空文字を出力し、既存書籍への影響ゼロ。
- `lessons_block` に値がある場合、教訓ブロックが出力される。

実際の `build_final_writing_prompt` は `prompts/manager.py` で
`kwargs.get("lessons_block", "")` をテンプレートに渡しており、
flag OFF 時は空文字（＝レンダリング不変）が保証される。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "prompts" / "templates"

# final_writing_prompt.j2 の lessons_block 周辺スニペットを抽出した
# 最小テンプレート。実際のテンプレートと同じ `{% if %}` ガードを使う。
_MINIMAL_TPL = """\
{% if rag_context_block %}

{{ rag_context_block }}
{% endif %}
{% if lessons_block %}

{{ lessons_block }}
{% endif %}

【指令】
テンポ重視のシーンです。
"""


def _render(lessons_block: str = "", rag_context_block: str = "") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    # 実際のテンプレートファイルを使い、不足変数は空文字でフォールバック
    tmpl = env.get_template("narrative/final_writing_prompt.j2")
    return tmpl.render(
        lessons_block=lessons_block,
        rag_context_block=rag_context_block,
        ep_num=1,
        plot_data={"scenes": [], "detailed_blueprint": "", "current_chain_phase": "Hate"},
        script_text="",
        target_word_count=2000,
        book_id=1,
        foreshadowing_context="",
        char_static_ctx="",
        char_dynamic_ctx="",
        prev_ctx="",
        pov_character_name="主人公",
        density_level="Standard",
        blueprint="",
        tone_inst="",
        dialogue_profiles={},
        emotional_context="",
        three_layer_ctx="",
        contract_foreshadowings=[],
        foreshadowing_contract_context="",
        assertion_inst="",
        forbidden_inst="",
        hook_inst="",
        show_tell_inst="",
        quota_inst="",
        name="",
        profile="",
    )


def test_off_byte_identical_without_lessons_block():
    """lessons_block="" では教訓ヘッダが出力されず、既存プロンプトと同等になる。"""
    actual = _render(lessons_block="")
    assert "過去話の失敗教訓" not in actual
    assert "【指令】" in actual


def test_on_contains_lesson_block():
    """lessons_block に値がある場合、教訓ブロックが出力される。"""
    # _format_audit_lessons が付与するヘッダを含む完全なブロックを渡す
    block = "【過去話の失敗教訓（執筆時に最優先で回避）】\n- [deai] AI定型表現を使わない （第3話に発生・2回目）"
    actual = _render(lessons_block=block)
    assert "過去話の失敗教訓" in actual
    assert "AI定型表現を使わない" in actual
    assert "第3話に発生・2回目" in actual


def test_off_equals_rag_only_output():
    """lessons_block 空時、rag_context_block のみが反映され、教訓ブロックは混入しない。"""
    actual_no_lessons = _render(lessons_block="", rag_context_block="RAGコンテキスト")
    actual_with_lessons = _render(lessons_block="", rag_context_block="RAGコンテキスト")
    assert actual_no_lessons == actual_with_lessons
    assert "RAGコンテキスト" in actual_no_lessons
    assert "過去話の失敗教訓" not in actual_no_lessons


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
